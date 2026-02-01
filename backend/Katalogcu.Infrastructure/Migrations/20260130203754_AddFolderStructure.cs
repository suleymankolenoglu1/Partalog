using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Katalogcu.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddFolderStructure : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<Guid>(
                name: "FolderId",
                table: "Catalogs",
                type: "uuid",
                nullable: true);

            migrationBuilder.CreateTable(
                name: "Folder",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Name = table.Column<string>(type: "text", nullable: false),
                    UserId = table.Column<Guid>(type: "uuid", nullable: false),
                    CreatedDate = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Folder", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Catalogs_FolderId",
                table: "Catalogs",
                column: "FolderId");

            migrationBuilder.AddForeignKey(
                name: "FK_Catalogs_Folder_FolderId",
                table: "Catalogs",
                column: "FolderId",
                principalTable: "Folder",
                principalColumn: "Id");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_Catalogs_Folder_FolderId",
                table: "Catalogs");

            migrationBuilder.DropTable(
                name: "Folder");

            migrationBuilder.DropIndex(
                name: "IX_Catalogs_FolderId",
                table: "Catalogs");

            migrationBuilder.DropColumn(
                name: "FolderId",
                table: "Catalogs");
        }
    }
}
