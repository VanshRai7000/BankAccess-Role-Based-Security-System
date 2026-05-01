// Live clock
function updateClock() {
  const el = document.getElementById('clock');
  if (el) {
    const now = new Date();
    el.textContent = now.toLocaleString('en-IN', {
      weekday: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  }
}
setInterval(updateClock, 1000);
updateClock();

// Auto-dismiss alerts after 4s
document.querySelectorAll('.alert').forEach(alert => {
  setTimeout(() => {
    alert.style.transition = 'opacity .5s';
    alert.style.opacity = '0';
    setTimeout(() => alert.remove(), 500);
  }, 4000);
});

// Amount formatter — add ₹ symbol hint while typing
const amountInput = document.getElementById('amount');
if (amountInput) {
  amountInput.addEventListener('input', function () {
    if (this.value < 0) this.value = 0;
  });
}
