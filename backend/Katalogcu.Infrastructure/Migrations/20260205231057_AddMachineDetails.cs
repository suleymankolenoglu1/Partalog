using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Katalogcu.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddMachineDetails : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "Dimensions",
                table: "CatalogItems",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "MachineBrand",
                table: "CatalogItems",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "MachineModel",
                table: "CatalogItems",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Mechanism",
                table: "CatalogItems",
                type: "text",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "Dimensions",
                table: "CatalogItems");

            migrationBuilder.DropColumn(
                name: "MachineBrand",
                table: "CatalogItems");

            migrationBuilder.DropColumn(
                name: "MachineModel",
                table: "CatalogItems");

            migrationBuilder.DropColumn(
                name: "Mechanism",
                table: "CatalogItems");
        }
    }
}
