

using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;

namespace Katalogcu.API.Controllers
{
    [Route("api/[controller]")]
    [ApiController]
    public class AuthController: ControllerBase
    {
        private readonly AppDbContext _context;
        private readonly IConfiguration _configuration;

        public AuthController(AppDbContext context, IConfiguration configuration)
        {
            _context = context;
            _configuration = configuration;
        }


        public record LoginRequest(string Email, string Password);
        public record RegisterRequest(string FullName, string Email, string Password);

        [HttpPost("login")]
        public async Task<IActionResult> Login([FromBody] LoginRequest request)
        {
            // 1. Kullanıcıyı veritabanında bul
            var user = await _context.Users.FirstOrDefaultAsync(u => u.Email == request.Email);

            // 2. Kullanıcı yoksa veya şifre yanlışsa hata dön
            // (Not: Şimdilik şifreyi düz metin kontrol ediyoruz, ilerde Hashleyeceğiz)
            if (user == null || user.PasswordHash != request.Password)
            {
                return Unauthorized(new { message = "Email veya şifre hatalı!" });
            }

            // 3. Token Oluşturma (JWT)
            var tokenHandler = new JwtSecurityTokenHandler();
            var key = Encoding.ASCII.GetBytes(_configuration["JwtSettings:SecretKey"]!);

            var tokenDescriptor = new SecurityTokenDescriptor
            {
                Subject = new ClaimsIdentity(new[]
                {
                    new Claim(ClaimTypes.NameIdentifier, user.Id.ToString()),
                    new Claim(ClaimTypes.Email, user.Email),
                    new Claim(ClaimTypes.Role, user.Role)
                }),
                Expires = DateTime.UtcNow.AddDays(7), // Token 7 gün geçerli
                Issuer = _configuration["JwtSettings:Issuer"],
                Audience = _configuration["JwtSettings:Audience"],
                SigningCredentials = new SigningCredentials(new SymmetricSecurityKey(key), SecurityAlgorithms.HmacSha256Signature)
            };

            var token = tokenHandler.CreateToken(tokenDescriptor);
            var tokenString = tokenHandler.WriteToken(token);

            // 4. Token'ı ve kullanıcı bilgisini dön
            return Ok(new 
            { 
                Token = tokenString, 
                User = new { user.FirstName, user.LastName, user.Email, user.Role } 
            });
        }

       
    

    

         [HttpPost("register")]
         public async Task<IActionResult> Register([FromBody] RegisterRequest request)
    {
        // 1. Bu email daha önce alınmış mı kontrol et
        if (await _context.Users.AnyAsync(u => u.Email == request.Email))
        {
            return BadRequest(new { message = "Bu e-posta adresi zaten kayıtlı!" });
        }

        // 2. İsim Soyisim Ayrıştırma (Basit yöntem)
        var names = request.FullName.Split(' ', 2);
        var firstName = names[0];
        var lastName = names.Length > 1 ? names[1] : "";

        // 3. Yeni Kullanıcı Oluştur
        var newUser = new AppUser
        {
            FirstName = firstName,
            LastName = lastName,
            Email = request.Email,
            PasswordHash = request.Password, // Not: Gerçek projede burası Hash'lenmeli (BCrypt vb.)
            Role = "Customer", // Varsayılan rol Müşteri
            CreatedDate = DateTime.UtcNow
        };

        _context.Users.Add(newUser);
        await _context.SaveChangesAsync();

        return Ok(new { message = "Kayıt başarılı! Giriş yapabilirsiniz." });
    }



    }
}