const $ = id => document.getElementById(id);
let selectedVideo = null;
let mode = "video";

document.querySelectorAll(".mode").forEach(button => {
  button.addEventListener("click", () => {
    mode = button.dataset.mode;
    document.querySelectorAll(".mode").forEach(item => item.classList.toggle("active", item === button));
    $("videoMode").hidden = mode !== "video";
    $("promptMode").hidden = mode !== "prompt";
    $("download").hidden = true;
    $("status").textContent = "";
  });
});

$("video").addEventListener("change", event => {
  selectedVideo = event.target.files && event.target.files[0];
  if (!selectedVideo) return;
  $("filename").textContent = selectedVideo.name;
  $("preview").src = URL.createObjectURL(selectedVideo);
  $("preview").style.display = "block";
  $("download").hidden = true;
});

$("render").addEventListener("click", async () => {
  if (mode === "video" && !selectedVideo) {
    $("status").textContent = "Choose a video clip first.";
    return;
  }
  if (mode === "prompt" && !$("prompt").value.trim() && !$("headline").value.trim()) {
    $("status").textContent = "Describe the animation or enter a headline first.";
    return;
  }

  const button = $("render");
  button.disabled = true;
  button.textContent = "Creating your motion graphic…";
  $("download").hidden = true;
  $("status").textContent = "Preparing your design and rendering. Please keep this page open.";

  const form = new FormData();
  if (selectedVideo && mode === "video") form.append("video", selectedVideo);
  form.append("mode", mode);
  ["prompt", "headline", "subheading", "style", "position", "resolution"].forEach(key => form.append(key, $(key).value));
  form.append("output_mode", $("output").value);

  try {
    const response = await fetch("/api/render", { method: "POST", body: form });
    let result;
    try { result = await response.json(); }
    catch { throw new Error("The server returned an unreadable response (" + response.status + "). Check Render logs."); }
    if (!response.ok) throw new Error(result.detail || ("Server error (" + response.status + ")"));
    $("download").href = result.download_url;
    $("download").download = result.filename;
    $("download").hidden = false;
    $("status").textContent = "Render complete · " + result.mode + " mode · " + result.style + " · " + result.resolution + "\n" + result.note;
  } catch (error) {
    $("status").textContent = "Could not render: " + error.message;
  } finally {
    button.disabled = false;
    button.textContent = "✦ Generate motion graphics";
  }
});