<script lang="ts">
  import "../app.css";
  let { children } = $props();
</script>

<svelte:head>
  <title>NMS Save Editor</title>
</svelte:head>

<div class="flex h-screen overflow-hidden" style="background: var(--background); color: var(--foreground);">
  {@render children()}
</div>
