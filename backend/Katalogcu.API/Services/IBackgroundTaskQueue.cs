using System;
using System.Threading;
using System.Threading.Tasks;

namespace Katalogcu.API.Services
{
    public interface IBackgroundTaskQueue
    {
        // Kuyruğa yeni iş eklemek için (Garson kullanacak)
        ValueTask QueueBackgroundWorkItemAsync(Func<CancellationToken, ValueTask> workItem);

        // Kuyruktan iş çekmek için (Usta kullanacak)
        ValueTask<Func<CancellationToken, ValueTask>> DequeueAsync(CancellationToken cancellationToken);
    }
}