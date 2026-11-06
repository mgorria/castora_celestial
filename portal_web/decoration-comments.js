(function (root) {
  'use strict';

  // Only confirmed decorations and optional ideas belong in this public copy.
  const observations = [
    ['Ya en casa', 'Ese camino de mesa navideño nuevo y semejante guirnalda… La mesa del salón se ha presentado al concurso por su cuenta.'],
    ['Una idea', 'Un protector de sofá navideño podría tener su gracia. El sofá lleva un rato viendo cómo se arreglan todos los demás.'],
    ['Ya en casa', 'Más “preciosas” en la terraza. Con ese nombre venían con ventaja, muuu.'],
    ['Una idea', 'Una vajilla navideña podría rematar esa mesa. La guirnalda ya ha hecho una entrada espectacular.'],
    ['Ya en casa', 'Más velas LED: aquí hasta los rincones están ensayando su cara de Navidad.'],
    ['Una idea', 'Si apetece otro detalle para la mesa, una cubertería festiva podría acompañarla. Los tenedores también tienen derecho a presumir.'],
    ['Ya en casa', 'La tira de luces del dormitorio también cuenta. El jurado no se queda solo en el salón.'],
    ['Una idea', 'Unas fundas de cojín navideñas serían otro guiño para el salón. El sofá podría presumir sin cambiarse entero.'],
    ['Ya en casa', 'Cascabeles en la entrada. Estupendos para la Navidad y bastante incómodos para quien pretenda entrar de puntillas.'],
    ['Una idea', 'Unas servilletas con un lazo podrían acompañar el camino de mesa. Algo pequeño: esa guirnalda ya sabe llamar la atención.'],
    ['Ya en casa', 'Entre la guirnalda, las “preciosas” y los cascabeles, esta casa está reuniendo pruebas muuuuy convincentes.'],
    ['Una idea', 'Con lo que ya hay, probaría a encender las “preciosas” y las velas LED al caer la tarde. A veces el truco está en cómo luce todo junto.']
  ];
  let section = null, button = null, index = 0;

  function render() {
    const [label, comment] = observations[0];
    return `<div class="decoration-comments" data-decoration-comments>
      <p class="decoration-comments-heading">La Vaca toma nota</p>
      <div class="decoration-comments-observation" aria-live="polite" aria-atomic="true">
        <span class="decoration-comments-label" data-decoration-comment-label>${label}</span>
        <p class="decoration-comments-quote" data-decoration-comment-text>«${comment}»</p>
      </div>
      <button class="decoration-comments-next" type="button" data-decoration-comment-next>Otra observación <span aria-hidden="true">↗</span></button>
    </div>`;
  }

  function next() {
    if (!section?.isConnected) { unmount(); return; }
    index = (index + 1) % observations.length;
    const [label, comment] = observations[index];
    section.querySelector('[data-decoration-comment-label]').textContent = label;
    section.querySelector('[data-decoration-comment-text]').textContent = `«${comment}»`;
  }

  function unmount() {
    if (button) button.removeEventListener('click', next);
    section = button = null;
  }

  function mount(node) {
    unmount();
    section = node;
    if (!section) return;
    index = 0;
    section.querySelector('[data-decoration-comment-label]').textContent = observations[0][0];
    section.querySelector('[data-decoration-comment-text]').textContent = `«${observations[0][1]}»`;
    button = section.querySelector('[data-decoration-comment-next]');
    button.addEventListener('click', next);
  }

  root.CastoriDecorationComments = { render, mount, unmount };
})(typeof window === 'undefined' ? globalThis : window);
