document.addEventListener("DOMContentLoaded", () => {
  const quizForm = document.getElementById("quiz-form");
  if (quizForm) {
    const radios = quizForm.querySelectorAll('input[type="radio"]');
    const progressFill = document.getElementById("quiz-progress-fill");
    const totalQuestions = quizForm.querySelectorAll(".question-card").length;
    const submitBtn = document.getElementById("quiz-submit-btn");
    const updateProgress = () => {
      const answered = new Set([...radios].filter(r => r.checked).map(r => r.name));
      if (progressFill) progressFill.style.width = `${Math.round(answered.size / totalQuestions * 100)}%`;
      if (submitBtn) submitBtn.disabled = answered.size < totalQuestions;
    };
    radios.forEach(radio => radio.addEventListener("change", () => {
      const card = radio.closest(".question-card"); card.querySelectorAll(".option").forEach(opt => opt.classList.remove("selected"));
      radio.closest(".option").classList.add("selected"); updateProgress();
    }));
    quizForm.addEventListener("submit", event => {
      if (submitBtn.disabled) { event.preventDefault(); return; }
      if (!navigator.onLine) {
        event.preventDefault();
        const queued = JSON.parse(localStorage.getItem("learnsphere-pending-quizzes") || "[]");
        queued.push({action: quizForm.action, entries: [...new FormData(quizForm).entries()]});
        localStorage.setItem("learnsphere-pending-quizzes", JSON.stringify(queued));
        submitBtn.textContent = "Saved for submission when online"; submitBtn.disabled = true;
      }
    });
    updateProgress();
    const timer = document.querySelector(".challenge-timer");
    if (timer) { let seconds = Number(timer.dataset.seconds); const output = document.getElementById("time-left"); const clock = setInterval(() => { seconds--; output.textContent = seconds; if (seconds <= 0) { clearInterval(clock); quizForm.submit(); } }, 1000); }
  }
  document.querySelectorAll(".tutor-panel").forEach(panel => {
    const form = panel.querySelector(".tutor-form"); if (!form) return;
    form.addEventListener("submit", async event => { event.preventDefault(); const answer = panel.querySelector(".tutor-answer"); const button = form.querySelector("button"); button.disabled = true; answer.textContent = "Thinking…";
      try { const response = await fetch(`/tutor/${panel.dataset.tutorTopic}`, {method: "POST", body: new FormData(form)}); const data = await response.json(); answer.textContent = data.answer || data.error || "Tutor is unavailable right now."; } catch { answer.textContent = "Tutor is unavailable right now."; } button.disabled = false; });
  });
  document.querySelectorAll(".reveal-card").forEach(button => button.addEventListener("click", () => { button.hidden = true; button.nextElementSibling.hidden = false; }));
  document.querySelectorAll(".review-actions button").forEach(button => button.addEventListener("click", async () => { const card = button.closest(".flashcard"); button.disabled = true; const response = await fetch(`/flashcards/${card.dataset.questionId}/review`, {method: "POST", headers: {"Content-Type": "application/x-www-form-urlencoded"}, body: `quality=${button.dataset.quality}`}); const data = await response.json(); card.innerHTML = `<p class="reviewed">✓ ${data.next_review || "Saved"}</p>`; }));
  const replayPendingQuizzes = async () => {
    const queued = JSON.parse(localStorage.getItem("learnsphere-pending-quizzes") || "[]");
    if (!queued.length || !navigator.onLine) return;
    const remaining = [];
    for (const item of queued) {
      try { const response = await fetch(item.action, {method: "POST", body: new URLSearchParams(item.entries), credentials: "same-origin"}); if (!response.ok) remaining.push(item); } catch { remaining.push(item); }
    }
    localStorage.setItem("learnsphere-pending-quizzes", JSON.stringify(remaining));
  };
  window.addEventListener("online", replayPendingQuizzes); replayPendingQuizzes();
});
