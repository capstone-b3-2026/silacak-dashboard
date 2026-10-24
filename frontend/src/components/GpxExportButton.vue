<template>
  <a :href="gpxDownloadUrl(hikerCode)" download class="gpx-btn"> Export GPX — {{ hikerCode }} </a>
</template>

<script setup>
import { gpxDownloadUrl } from "../services/api";

defineProps({
  hikerCode: {
    type: String,
    required: true,
  },
});
</script>

<style scoped>
.gpx-btn {
  display: inline-block;
  background: transparent;
  color: var(--blue-fg);
  border: 1px solid var(--blue-fg);
  border-radius: 8px;
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
  font-family: inherit;
}
.gpx-btn:hover {
  background: var(--btn);
  border-color: var(--btn);
  color: var(--on-btn);
}
</style>