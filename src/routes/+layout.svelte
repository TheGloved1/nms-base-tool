<script lang="ts">
  import "../app.css";
  let { children } = $props();
</script>

<svelte:head>
  <title>NMSBT — NMS Base Tool</title>
</svelte:head>

<div class="flex h-screen overflow-hidden" style="background: var(--background); color: var(--foreground);">
  {@render children()}
</div>
