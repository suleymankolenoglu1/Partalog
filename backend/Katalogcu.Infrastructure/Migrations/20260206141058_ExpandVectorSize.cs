using Microsoft.EntityFrameworkCore.Migrations;
using Pgvector;

#nullable disable

namespace Katalogcu.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class ExpandVectorSize : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AlterColumn<Vector>(
                name: "Embedding",
                table: "CatalogItems",
                type: "vector(3072)",
                nullable: true,
                oldClrType: typeof(Vector),
                oldType: "vector(768)",
                oldNullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AlterColumn<Vector>(
                name: "Embedding",
                table: "CatalogItems",
                type: "vector(768)",
                nullable: true,
                oldClrType: typeof(Vector),
                oldType: "vector(3072)",
                oldNullable: true);
        }
    }
}
