using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using System;
using System.Threading;
using System.Threading.Tasks;

namespace Katalogcu.API.Services
{
    public class QueuedHostedService : BackgroundService
    {
        private readonly IBackgroundTaskQueue _taskQueue;
        private readonly ILogger<QueuedHostedService> _logger;

        public QueuedHostedService(IBackgroundTaskQueue taskQueue, ILogger<QueuedHostedService> logger)
        {
            _taskQueue = taskQueue;
            _logger = logger;
        }

        protected override async Task ExecuteAsync(CancellationToken stoppingToken)
        {
            _logger.LogInformation("🔥 Arka Plan İşçisi (Worker) Başladı ve İş Bekliyor...");

            while (!stoppingToken.IsCancellationRequested)
            {
                // 1. Kuyruktan iş al (İş yoksa burada uyur bekler)
                var workItem = await _taskQueue.DequeueAsync(stoppingToken);

                try
                {
                    // 2. İşi çalıştır
                    await workItem(stoppingToken);
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "❌ Kuyruktaki iş yapılırken hata oluştu.");
                }
            }
        }
    }
}