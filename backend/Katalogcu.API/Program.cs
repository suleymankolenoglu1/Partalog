using Katalogcu.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using System.Text.Json.Serialization;
using System.Text;
using Microsoft.OpenApi.Models;
using Microsoft.IdentityModel.Tokens;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Katalogcu.API.Services; // PartalogAiService burada olmalı

var builder = WebApplication.CreateBuilder(args);

// 1. Servislerin Eklendiği Bölüm
// --------------------------------------------------------

// Yardımcı Servisler
builder.Services.AddScoped<PdfService>();
builder.Services.AddScoped<ExcelService>();

// --- YENİ AI SERVİS ENTEGRASYONU (BAŞLANGIÇ) ---

// appsettings.json dosyasından "AiService" ayarlarını çekiyoruz
var aiConfig = builder.Configuration.GetSection("AiService");
string aiBaseUrl = aiConfig["BaseUrl"] ?? "http://localhost:8000"; // Varsayılan Python adresi

// Merkezi AI Servisini HttpClient ile Kaydediyoruz
builder.Services.AddHttpClient<IPartalogAiService, PartalogAiService>(client =>
{
    client.BaseAddress = new Uri(aiBaseUrl);
    // Gemini bazen büyük/karışık görsellerde düşünebilir, süre tanıyalım.
    client.Timeout = TimeSpan.FromMinutes(2); 
});

// --- YENİ AI SERVİS ENTEGRASYONU (BİTİŞ) ---


builder.Services.AddControllers().AddJsonOptions(options =>
{
    // İlişkisel verilerde sonsuz döngüyü engeller (Parent -> Child -> Parent)
    options.JsonSerializerOptions.ReferenceHandler = ReferenceHandler.IgnoreCycles;
});

// Veritabanı Bağlantısı
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

// Swagger Konfigürasyonu (Auth Desteği ile)
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(c =>
{
    c.AddSecurityDefinition("Bearer", new OpenApiSecurityScheme
    {
        Description = "JWT Authorization header using the Bearer scheme. (Örnek: 'Bearer 12345abcdef')",
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
                Reference = new OpenApiReference
                {
                    Type = ReferenceType.SecurityScheme,
                    Id = "Bearer"
                },
                Scheme = "oauth2",
                Name = "Bearer",
                In = ParameterLocation.Header,
            },
            new List<string>()
        }
    });
});

// CORS Ayarları (Frontend Erişimi İçin)
builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowAngularApp",
        policy =>
        {
            policy.WithOrigins("http://localhost:4200") // Angular'ın adresi
                  .AllowAnyHeader()
                  .AllowAnyMethod();
        });
});

var app = builder.Build();

// 2. Uygulama Çalışma Anı (Middleware)
// --------------------------------------------------------

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseCors("AllowAngularApp");

app.UseHttpsRedirection();

app.UseStaticFiles();

// Auth Middleware Sırası Önemlidir!
app.UseAuthentication(); // Önce kimlik doğrula
app.UseAuthorization();  // Sonra yetki ver

app.MapControllers();

app.Run();