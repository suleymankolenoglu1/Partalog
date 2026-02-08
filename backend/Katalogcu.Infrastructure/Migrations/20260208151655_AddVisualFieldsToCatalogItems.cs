using Microsoft.EntityFrameworkCore.Migrations;
using Pgvector;

#nullable disable

namespace Katalogcu.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddVisualFieldsToCatalogItems : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "VisualBbox",
                table: "CatalogItems",
                type: "jsonb",
                nullable: true);

            migrationBuilder.AddColumn<Vector>(
                name: "VisualEmbedding",
                table: "CatalogItems",
                type: "vector(3072)",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "VisualOcrText",
                table: "CatalogItems",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "VisualPageNumber",
                table: "CatalogItems",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "VisualShapeTags",
                table: "CatalogItems",
                type: "jsonb",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "VisualBbox",
                table: "CatalogItems");

            migrationBuilder.DropColumn(
                name: "VisualEmbedding",
                table: "CatalogItems");

            migrationBuilder.DropColumn(
                name: "VisualOcrText",
                table: "CatalogItems");

            migrationBuilder.DropColumn(
                name: "VisualPageNumber",
                table: "CatalogItems");

            migrationBuilder.DropColumn(
                name: "VisualShapeTags",
                table: "CatalogItems");
        }
    }
}
