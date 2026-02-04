using System;
using System.Threading;
using System.Threading.Channels; // 🔥 Sihirli kütüphane bu
using System.Threading.Tasks;

namespace Katalogcu.API.Services
{
    public class BackgroundTaskQueue : IBackgroundTaskQueue
    {
        private readonly Channel<Func<CancellationToken, ValueTask>> _queue;

        public BackgroundTaskQueue(int capacity)
        {
            // Kapasiteyi belirliyoruz (Örn: Sırada en fazla 100 dosya bekleyebilir)
            // Bellek şişmesin diye sınır koymak iyidir.
            var options = new BoundedChannelOptions(capacity)
            {
                FullMode = BoundedChannelFullMode.Wait // Kuyruk doluysa beklet
            };
            _queue = Channel.CreateBounded<Func<CancellationToken, ValueTask>>(options);
        }

        public async ValueTask QueueBackgroundWorkItemAsync(Func<CancellationToken, ValueTask> workItem)
        {
            if (workItem == null) throw new ArgumentNullException(nameof(workItem));
            await _queue.Writer.WriteAsync(workItem);
        }

        public async ValueTask<Func<CancellationToken, ValueTask>> DequeueAsync(CancellationToken cancellationToken)
        {
            // İş gelene kadar burada bekler (CPU yormaz)
            return await _queue.Reader.ReadAsync(cancellationToken);
        }
    }
}