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
  background: #2f81f7;
  color: white;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  text-decoration: none;
  font-family: system-ui, sans-serif;
}
.gpx-btn:hover {
  background: #1f6feb;
}
</style>
