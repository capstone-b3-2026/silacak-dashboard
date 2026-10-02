import { onMounted, onUnmounted } from "vue";

/**
 * Konsumsi SSE dari /api/v1/stream. EventSource browser sudah handle
 * auto-reconnect bawaan, tapi kita tambah retry manual juga buat
 * jaga-jaga kalau backend sempat restart.
 */
export function useLiveStream(onMessage) {
  let source = null;

  const connect = () => {
    source = new EventSource("/api/v1/stream");

    source.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data));
      } catch (err) {
        console.error("Gagal parse event SSE:", err);
      }
    };

    source.onerror = () => {
      source?.close();
      setTimeout(connect, 2000);
    };
  };

  onMounted(connect);
  onUnmounted(() => source?.close());
}
