using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Katalogcu.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddPageNumberToProduct : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "PageNumber",
                table: "Products",
                type: "text",
                nullable: false,
                defaultValue: "");

            migrationBuilder.AddColumn<int>(
                name: "RefNo",
                table: "Products",
                type: "integer",
                nullable: false,
                defaultValue: 0);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "PageNumber",
                table: "Products");

            migrationBuilder.DropColumn(
                name: "RefNo",
                table: "Products");
        }
    }
}
