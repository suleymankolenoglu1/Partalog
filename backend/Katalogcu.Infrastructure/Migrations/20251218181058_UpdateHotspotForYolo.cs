using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Katalogcu.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class UpdateHotspotForYolo : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "Number",
                table: "Hotspots");

            migrationBuilder.RenameColumn(
                name: "Y",
                table: "Hotspots",
                newName: "Width");

            migrationBuilder.RenameColumn(
                name: "X",
                table: "Hotspots",
                newName: "Top");

            migrationBuilder.AddColumn<double>(
                name: "AiConfidence",
                table: "Hotspots",
                type: "double precision",
                nullable: false,
                defaultValue: 0.0);

            migrationBuilder.AddColumn<double>(
                name: "Height",
                table: "Hotspots",
                type: "double precision",
                nullable: false,
                defaultValue: 0.0);

            migrationBuilder.AddColumn<bool>(
                name: "IsAiDetected",
                table: "Hotspots",
                type: "boolean",
                nullable: false,
                defaultValue: false);

            migrationBuilder.AddColumn<string>(
                name: "Label",
                table: "Hotspots",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<double>(
                name: "Left",
                table: "Hotspots",
                type: "double precision",
                nullable: false,
                defaultValue: 0.0);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "AiConfidence",
                table: "Hotspots");

            migrationBuilder.DropColumn(
                name: "Height",
                table: "Hotspots");

            migrationBuilder.DropColumn(
                name: "IsAiDetected",
                table: "Hotspots");

            migrationBuilder.DropColumn(
                name: "Label",
                table: "Hotspots");

            migrationBuilder.DropColumn(
                name: "Left",
                table: "Hotspots");

            migrationBuilder.RenameColumn(
                name: "Width",
                table: "Hotspots",
                newName: "Y");

            migrationBuilder.RenameColumn(
                name: "Top",
                table: "Hotspots",
                newName: "X");

            migrationBuilder.AddColumn<int>(
                name: "Number",
                table: "Hotspots",
                type: "integer",
                nullable: false,
                defaultValue: 0);
        }
    }
}
