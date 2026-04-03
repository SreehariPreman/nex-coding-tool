document.getElementById('loginForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const resp = await fetch('/api/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password })
    });
    const data = await resp.json();
    const loginMessage = document.getElementById('loginMessage');
    if (data.success) {
        loginMessage.style.color = 'green';
        loginMessage.textContent = 'Login successful!';
        document.getElementById('loginForm').style.display = 'none';
    } else {
        loginMessage.style.color = 'red';
        loginMessage.textContent = 'Invalid username or password';
    }
});
