<script lang="ts">
  import "../app.css";
  import { onMount } from "svelte";
  import { applyUiSettings, loadUiSettings } from "$lib/settings";
  let { children } = $props();

  onMount(() => {
    (async () => {
      try {
        const s = await loadUiSettings();
        applyUiSettings(s.theme, s.font);
      } catch {}
    })();
  });
</script>

<svelte:head>
  <title>NMSBT — NMS Base Tool</title>
</svelte:head>

<div class="flex h-screen overflow-hidden bg-background text-foreground">
  {@render children()}
</div>
