using Katalogcu.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using System.Text.Json.Serialization;
using System.Text;
using Microsoft.OpenApi.Models;
using Microsoft.IdentityModel.Tokens;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Katalogcu.API.Services;
using Microsoft.AspNetCore.Http.Features; 
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Polly; // 🔥 Polly için
using Polly.Extensions.Http; // 🔥 Polly HTTP Extensions için

var builder = WebApplication.CreateBuilder(args);

// ========================================================
// 1. SERVİSLERİN KAYDEDİLMESİ (DEPENDENCY INJECTION)
// ========================================================

// BÜYÜK DOSYA YÜKLEME LİMİTLERİ (PDF/Resim için)
builder.Services.Configure<FormOptions>(options =>
{
    options.ValueLengthLimit = int.MaxValue;
    options.MultipartBodyLengthLimit = int.MaxValue;
    options.MemoryBufferThreshold = int.MaxValue;
});

builder.Services.Configure<KestrelServerOptions>(options =>
{
    options.Limits.MaxRequestBodySize = int.MaxValue;
});

// Genel HttpClient Fabrikası
builder.Services.AddHttpClient(); 

// Yardımcı Servisler
builder.Services.AddScoped<PdfService>();
builder.Services.AddScoped<ExcelService>();
builder.Services.AddScoped<CatalogProcessorService>();

// 🔥 KUYRUK SİSTEMİ (BACKGROUND JOB) 🔥
// 1. Kuyruğu Singleton yapıyoruz (Tüm uygulama aynı sırayı kullansın)
builder.Services.AddSingleton<IBackgroundTaskQueue>(ctx => 
{
    return new BackgroundTaskQueue(100); // Kapasite: 100 Dosya
});

// 2. Arka Plan İşçisini (Worker) başlatıyoruz
builder.Services.AddHostedService<QueuedHostedService>();


// 🔥 AI SERVİS ENTEGRASYONU (POLLY İLE GÜÇLENDİRİLDİ) 🔥
builder.Services.AddHttpClient<IPartalogAiService, PartalogAiService>(client =>
{
    client.BaseAddress = new Uri("http://127.0.0.1:8000/"); 
    client.Timeout = TimeSpan.FromMinutes(10); // Timeout süresini biraz artırdık
})
.AddPolicyHandler(GetRetryPolicy()); // 👈 Hata Telafisi Eklendi

// Controller ve JSON Ayarları
builder.Services.AddControllers().AddJsonOptions(options =>
{
    options.JsonSerializerOptions.ReferenceHandler = ReferenceHandler.IgnoreCycles;
});

// 🔥 VERİTABANI BAĞLANTISI (PostgreSQL + Vektör Desteği) 🔥
builder.Services.AddDbContext<AppDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("DefaultConnection"), x => 
    {
        x.UseVector(); 
    }));

// JWT Authentication Ayarları
var jwtSettings = builder.Configuration.GetSection("JwtSettings");
var secretKey = Encoding.ASCII.GetBytes(jwtSettings["SecretKey"] ?? "bu_cok_gizli_ve_uzun_bir_test_anahtaridir_123456");

builder.Services.AddAuthentication(options =>
{
    options.DefaultAuthenticateScheme = JwtBearerDefaults.AuthenticationScheme;
    options.DefaultChallengeScheme = JwtBearerDefaults.AuthenticationScheme;
})
.AddJwtBearer(options =>
{
    options.RequireHttpsMetadata = false;
    options.SaveToken = true;
    options.TokenValidationParameters = new TokenValidationParameters
    {
        ValidateIssuerSigningKey = true,
        IssuerSigningKey = new SymmetricSecurityKey(secretKey),
        ValidateIssuer = true, 
        ValidIssuer = jwtSettings["Issuer"] ?? "KatalogcuAPI",
        ValidateAudience = true, 
        ValidAudience = jwtSettings["Audience"] ?? "KatalogcuClient",
        ValidateLifetime = true,
        ClockSkew = TimeSpan.Zero
    };
});

// Swagger Konfigürasyonu
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(c =>
{
    c.SwaggerDoc("v1", new OpenApiInfo { Title = "Katalogcu API", Version = "v1" });
    
    c.AddSecurityDefinition("Bearer", new OpenApiSecurityScheme
    {
        Description = "JWT Authorization header. Örnek: 'Bearer {token}'",
        Name = "Authorization",
        In = ParameterLocation.Header,
        Type = SecuritySchemeType.ApiKey,
        Scheme = "Bearer"
    });
    c.AddSecurityRequirement(new OpenApiSecurityRequirement()
    {
        {
            new OpenApiSecurityScheme
            {
                Reference = new OpenApiReference { Type = ReferenceType.SecurityScheme, Id = "Bearer" },
                Scheme = "oauth2", Name = "Bearer", In = ParameterLocation.Header,
            },
            new List<string>()
        }
    });
});

// CORS AYARLARI
builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowAngularApp",
        policy =>
        {
            policy.WithOrigins("http://localhost:4200", "http://localhost:4200/") 
                  .AllowAnyHeader()
                  .AllowAnyMethod()
                  .SetIsOriginAllowed(_ => true)
                  .AllowCredentials();
        });
});

var app = builder.Build();

// ========================================================
// 2. MIDDLEWARE
// ========================================================

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseStaticFiles(); 
app.UseCors("AllowAngularApp");
app.UseAuthentication(); 
app.UseAuthorization();  

app.MapControllers();

app.Run();


// ========================================================
// 🛠️ YARDIMCI METOTLAR (POLLY POLİTİKASI)
// ========================================================
static IAsyncPolicy<HttpResponseMessage> GetRetryPolicy()
{
    return HttpPolicyExtensions
        // 1. Geçici Hataları Yakala (5xx, 408 Request Timeout)
        .HandleTransientHttpError()
        // 2. VEYA Google "Çok İstek Attın" (429 Too Many Requests) derse yakala
        .OrResult(msg => msg.StatusCode == System.Net.HttpStatusCode.TooManyRequests)
        // 3. Bekle ve Tekrar Dene (Exponential Backoff)
        // İlk deneme: 2sn, İkinci: 4sn, Üçüncü: 8sn bekle.
        .WaitAndRetryAsync(3, retryAttempt => TimeSpan.FromSeconds(Math.Pow(2, retryAttempt)));
}