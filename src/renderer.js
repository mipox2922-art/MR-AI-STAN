const status = document.getElementById('status');
const speakButton = document.getElementById('speak');
const readyButton = document.getElementById('ready');

async function speak(text) {
  status.textContent = 'MR AI anazungumza...';
  const ok = await window.mrAI.speak(text);
  status.textContent = ok ? 'Nimemaliza. Nipo tayari.' : 'Sauti haikufanya kazi kwenye mfumo huu.';
}

speakButton.addEventListener('click', () => {
  speak('Habari Boss Ferisi. Mr AI yupo tayari kufanya kazi.');
});

readyButton.addEventListener('click', () => {
  status.textContent = 'Nipo online, Boss Ferisi.';
  speak('Nipo online Boss Ferisi. Niambie tufanye nini.');
});
