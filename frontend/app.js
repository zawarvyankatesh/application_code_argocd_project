const statuses = ["todo", "doing", "done"];
const notice = document.querySelector("#notice");

async function request(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...options.headers } });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch (_) { /* keep HTTP message */ }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function makeCard(task) {
  const card = document.createElement("article");
  card.className = "card";
  const title = document.createElement("p");
  title.textContent = task.title;
  const actions = document.createElement("div");
  actions.className = "card-actions";
  const select = document.createElement("select");
  select.setAttribute("aria-label", `Status for ${task.title}`);
  for (const status of statuses) {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = { todo: "To do", doing: "In progress", done: "Done" }[status];
    select.append(option);
  }
  select.value = task.status;
  select.addEventListener("change", async () => {
    try { await request(`/api/tasks/${task.id}`, { method: "PATCH", body: JSON.stringify({ status: select.value }) }); await loadTasks(); }
    catch (error) { notice.textContent = error.message; select.value = task.status; }
  });
  const remove = document.createElement("button");
  remove.className = "delete";
  remove.type = "button";
  remove.textContent = "×";
  remove.setAttribute("aria-label", `Delete ${task.title}`);
  remove.addEventListener("click", async () => {
    try { await request(`/api/tasks/${task.id}`, { method: "DELETE" }); await loadTasks(); }
    catch (error) { notice.textContent = error.message; }
  });
  actions.append(select, remove);
  card.append(title, actions);
  return card;
}

async function loadTasks() {
  try {
    const tasks = await request("/api/tasks");
    notice.textContent = "";
    document.querySelector("#task-count").textContent = `${tasks.length} task${tasks.length === 1 ? "" : "s"}`;
    for (const status of statuses) {
      const container = document.querySelector(`#cards-${status}`);
      const matching = tasks.filter(task => task.status === status);
      container.replaceChildren(...matching.map(makeCard));
      document.querySelector(`#count-${status}`).textContent = matching.length;
      if (!matching.length) {
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = status === "todo" ? "A clear horizon. Add a task to begin." : "Nothing here yet.";
        container.append(empty);
      }
    }
  } catch (error) { notice.textContent = `Could not load tasks: ${error.message}`; }
}

document.querySelector("#task-form").addEventListener("submit", async event => {
  event.preventDefault();
  const input = document.querySelector("#title");
  try {
    await request("/api/tasks", { method: "POST", body: JSON.stringify({ title: input.value }) });
    input.value = "";
    await loadTasks();
    input.focus();
  } catch (error) { notice.textContent = error.message; }
});

loadTasks();
