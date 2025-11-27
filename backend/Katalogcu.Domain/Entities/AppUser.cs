using Katalogcu.Domain.Common;

namespace Katalogcu.Domain.Entities
{
    public class AppUser : BaseEntity
    {
        public string FirstName {get;set;} = string.Empty;
        public string LastName {get;set;} = string.Empty;
        public string Email {get;set;} = string.Empty;
        public string PasswordHash {get;set;} = string.Empty;
        public string Role {get;set;} = "Customer";
        public string? CompanyName {get; set;} 
        
        
    }
}

