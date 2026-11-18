const form = document.querySelector('#loginForm');
const message = document.querySelector('#loginMessage');
form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  button.disabled = true;
  message.hidden = true;
  const fields = new FormData(form);
  try {
    const result = await fetch('/api/auth/login', {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: fields.get('username'), password: fields.get('password')})
    });
    const data = await result.json().catch(() => ({}));
    if (!result.ok) throw new Error(data.detail || 'Não foi possível entrar.');
    window.location.replace('/');
  } catch (error) {
    message.textContent = error.message;
    message.hidden = false;
    button.disabled = false;
  }
});
