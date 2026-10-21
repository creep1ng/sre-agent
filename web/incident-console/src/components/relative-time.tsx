import { useNow } from "@/hooks/use-now";
import { formatDayTime, formatRelative } from "@/lib/format";

export function RelativeTime({ at, className }: { at: number; className?: string }) {
  const now = useNow();
  return (
    <time dateTime={new Date(at).toISOString()} title={formatDayTime(at, now)} className={className}>
      {formatRelative(at, now)}
    </time>
  );
}
