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

var builder = WebApplication.CreateBuilder(args);

// ========================================================
// 1. SERVİSLERİN KAYDEDİLMESİ (DEPENDENCY INJECTION)
// ========================================================

// BÜYÜK DOSYA YÜKLEME LİMİTLERİ
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

// Yardımcı Servisler
builder.Services.AddScoped<PdfService>();
builder.Services.AddScoped<ExcelService>();
builder.Services.AddScoped<CatalogProcessorService>();

// AI SERVİS ENTEGRASYONU
var aiConfig = builder.Configuration.GetSection("AiService");
string aiBaseUrl = aiConfig["BaseUrl"] ?? "http://localhost:8000"; 

builder.Services.AddHttpClient<IPartalogAiService, PartalogAiService>(client =>
{
    client.BaseAddress = new Uri(aiBaseUrl);
    client.Timeout = TimeSpan.FromMinutes(5); 
});

// Controller ve JSON Ayarları
builder.Services.AddControllers().AddJsonOptions(options =>
{
    options.JsonSerializerOptions.ReferenceHandler = ReferenceHandler.IgnoreCycles;
});

// Veritabanı Bağlantısı (PostgreSQL)
builder.Services.AddDbContext<AppDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("DefaultConnection")));

// JWT Authentication Ayarları
var jwtSettings = builder.Configuration.GetSection("JwtSettings");
var secretKey = Encoding.ASCII.GetBytes(jwtSettings["SecretKey"]!);

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
        ValidIssuer = jwtSettings["Issuer"],
        ValidateAudience = true,
        ValidAudience = jwtSettings["Audience"],
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
        Description = "JWT Authorization header using the Bearer scheme. Örnek: 'Bearer {token}'",
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

// 🔥 CORS AYARLARI (GÜNCELLENDİ)
builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowAngularApp",
        policy =>
        {
            policy.WithOrigins("http://localhost:4200", "http://localhost:4200/") // Sondaki slash ihtimaline karşı
                  .AllowAnyHeader()
                  .AllowAnyMethod()
                  .SetIsOriginAllowed(_ => true); // Localhost'ta bazen IP üzerinden gelirse engellememesi için
        });
});

var app = builder.Build();

// ========================================================
// 2. MIDDLEWARE (UYGULAMA ÇALIŞMA ANI)
// ========================================================

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseStaticFiles(); 

// CORS Her zaman Auth'dan önce gelmelidir!
app.UseCors("AllowAngularApp");

// Lokal testlerde HTTPS yönlendirmesi bazen 'Connection Refused' hatası verebilir.
// Eğer sadece http://localhost:5159 üzerinden çalışacaksan burayı geçici olarak kapatabilirsin.
// app.UseHttpsRedirection(); 

app.UseAuthentication(); 
app.UseAuthorization();  

app.MapControllers();

app.Run();