(function () {
  'use strict';

  const characters = {
    castori: {
      name: 'Oficina Castori',
      tagline: 'Los pequeños asuntos importantes',
      greeting: '¡Patita! Tu expediente de cosas bonitas ya está sobre mi mesa. He dejado un huequito entre los sellos para lo que quieras contarme. ¿Qué asunto tierno nos trae hoy por aquí?',
      suggestions: ['Quiero abrir un expediente bonito', 'Hoy necesito un poquito de ánimo', 'Cuéntame un cuento'],
      color: '#BC8057'
    },
    mimosuga: {
      name: 'Mimosuga',
      tagline: 'Aquí el tiempo va despacito',
      greeting: 'Ven, Patita, siéntate cerquita. Esta abuela tortuga tiene tiempo de sobra y una historia guardada en el bolsillo. Puedes empezar por donde quieras, sin correr.',
      suggestions: ['Hoy estoy un poco cansada', 'Me vendría bien un abrazo', 'Cuéntame un cuento de abuela'],
      color: '#829275'
    },
    salchicher: {
      name: 'Doctor Salchicher',
      tagline: 'Una consulta de ternura',
      greeting: '¡Adelante, Patita! Me acomodo las gafitas y abro la consulta de mimos. Este perrito tiene el cuaderno preparado para escucharte, un abrazo de los que no aprietan y un poquito de mojo de oso imaginario. ¿Cómo viene tu día?',
      suggestions: ['Necesito una pausa bonita', 'Ayúdame a celebrar algo pequeño', 'Cuéntame algo que dé alegría'],
      color: '#83A3AC'
    },
    vaca: {
      name: 'La Vaca Mágica',
      tagline: 'Profecías y secretos a medias',
      greeting: '¡Tolón, tolón, Patita! Se me ha escapado un poquito de purpurina iridiscente al encender las luces de Navidad. Aquí caben los deseos grandes, los pequeños y los que todavía no tienen nombre.',
      suggestions: ['¿Me susurras una profecía?', '¿Qué dice tu campanilla?', 'Quiero guardar un deseo'],
      color: '#A16C74'
    },
    dulcimiel: {
      name: 'Dulcimiel',
      tagline: 'Sabores de cuento, sin prisa',
      greeting: 'Hola, Patita. Soy Dulcimiel, la vaca prima de la Vaca Mágica. Me anudo mi pañuelo turquesa y abro el cuaderno de sabores imaginarios. ¿Exploramos juntas una historia dulce, sin ninguna prisa?',
      suggestions: ['Inventemos un sabor imaginario', 'Háblame de tu Navidad', 'Necesito unas palabras bonitas'],
      color: '#7BAAA4'
    }
  };

  const stories = [
    {
      id: 'el-boton-de-mimosuga',
      title: 'El botón que no tenía prisa',
      eyebrow: 'Un cuento de Mimosuga',
      body: 'Una tarde, Mimosuga encontró un botón azul debajo de su sillón. Era redondo como una gota de cielo y no pertenecía a ninguno de sus abrigos.\n\n—Pues tendremos que esperar a que nos cuente su historia —dijo la abuela tortuga.\n\nLo puso en un platito, junto a la ventana, y siguió remendando una manta. Patita le preguntó si no era mejor buscar enseguida de dónde había salido.\n\n—A veces, las cosas pequeñas aparecen cuando dejamos de revolver todos los cajones.\n\nPasó una nube. Sonó una cucharilla. El botón siguió quieto. Al caer la tarde, una ráfaga abrió el cuaderno de cuentos de Mimosuga por una página antigua. Allí había un dibujo de un bolsillo con un círculo azul y una frase: «Para guardar algo que todavía no sabemos».\n\nMimosuga sonrió. Cosió el botón a un pequeño sobre de tela y se lo entregó a Patita.\n\n—¿Y qué ponemos dentro?\n\n—Hoy, nada. Qué bonito es tener un sitio preparado.\n\nPatita dejó el sobre junto a su cama. A la mañana siguiente guardó en él una hoja con forma de corazón. El botón, que nunca había tenido prisa, encontró por fin algo que cuidar.'
    },
    {
      id: 'el-expediente-de-la-luz',
      title: 'El expediente de la luz de la tarde',
      eyebrow: 'Desde Oficina Castori',
      body: 'En Oficina Castori había archivadores para casi todo: los lunes torcidos, las ideas que llegan en la ducha y las meriendas que merecen una segunda servilleta. Pero aquella tarde entró por la ventana una franja de sol y nadie supo en qué carpeta guardarla.\n\nEl castor responsable de los sellos se puso muy serio. Sacó un formulario nuevo y escribió: «Asunto: una cosa bonita que dura poco».\n\nPatita acercó una silla a la luz.\n\n—Quizá no haya que guardarla en una carpeta.\n\nAquello no figuraba en el reglamento. Se celebró una reunión extraordinaria de tres minutos, con una galleta como orden del día. Después, el castor estampó su sello favorito sobre una hoja vacía: «AUTORIZADO DISFRUTAR».\n\nDurante un rato nadie movió papeles. Miraron cómo el sol avanzaba por el suelo hasta tocar la pata de la mesa. Afuera pasó alguien llevando flores. Dentro, una mota de polvo hizo una pirueta.\n\nCuando la luz desapareció, Patita escribió debajo del sello: «Estuvimos aquí».\n\nEl documento acabó en un archivador nuevo, de color albaricoque. En el lomo pusieron «Cosas que no podemos guardar, pero sí recordar». Y, por primera vez, aquel día la oficina cerró sin un solo asunto pendiente.'
    },
    {
      id: 'el-deseo-sin-lazo',
      title: 'El deseo que no necesitaba un lazo',
      eyebrow: 'Una historia de La Vaca Mágica',
      body: 'La Vaca Mágica estaba colocando pequeñas estrellas de papel cuando Patita apareció con un sobre sin dirección. Dentro había un deseo, escrito con letra muy pequeña.\n\n—No sé si este deseo sirve para Navidad —dijo Patita—. No se puede envolver.\n\nLa Vaca Mágica acercó una luz cálida al sobre.\n\n—Muchos de mis favoritos no caben en una caja.\n\nPatita había escrito: «Me gustaría tener una tarde tranquila con las personas que quiero». La vaca no prometió hacer aparecer aquella tarde. En cambio, puso una estrella junto al sobre y preguntó cómo sería.\n\nEntre las dos imaginaron una mesa algo desigual, tazas de distintos colores y una canción que alguien tarareaba sin conocer la letra. En su tarde inventada nadie tenía que decir nada extraordinario. Bastaba con acercar una silla.\n\nDespués hicieron una pequeña invitación de papel: «Cuando podamos, merendamos». Patita la guardó para decidir a quién enseñársela.\n\nLa Vaca Mágica volvió a colgar sus estrellas. Una quedó torcida y las dos decidieron dejarla así.\n\nEl deseo seguía siendo un deseo, con su futuro abierto. Pero ahora tenía una forma, una mesa y una primera frase. Y aquella noche, bajo la estrella torcida, eso ya parecía una cosa preciosa.'
    }
  ];

  const voice = {
    castori: {
      hello: ['¡Patita! Ventanilla de ternura abierta. Puedes dejar aquí una palabra, una alegría o ese pequeño lío que se ha colado en el día.', 'Qué alegría verte, Patita. He preparado una carpeta nueva: «Lo que me apetece contar hoy». Tú eliges la primera página.'],
      tired: ['Patita, abrimos un expediente de día a medio gas. En esta oficina también se aceptan las versiones pequeñas de las cosas. ¿Qué asunto te gustaría hacer más llevadero?', 'Anotado en el registro: hoy todo pesa un poquito más. Te acompaño con una frase de nuestro reglamento imaginario: «Lo pequeño también cuenta».'],
      sad: ['Te leo, Patita. No hace falta ponerle un sello alegre a un día triste. Si te apetece, cuéntame qué parte del día ha pesado más.', 'Abrimos una carpeta suave para esto, Patita. Puedes contarlo con todas sus comas o dejar solo una palabra. ¿Cuál sería hoy?'],
      thanks: ['Gracias a ti, Patita. Sello oficial: «Conversación recibida con cariño». Dejo la ventanilla abierta para tu siguiente idea.'],
      gift: ['Expediente de detalles bonitos abierto: una nota escrita a mano, una foto con una frase o una merienda compartida. ¿Para quién estamos imaginando el detalle?', 'Un regalo puede ser pequeñísimo y decir mucho, Patita. Propongo empezar por una frase: «Me acordé de ti cuando…».'],
      everyday: ['Resolución de Oficina Castori: el día no necesita ser extraordinario para merecer una página. ¿Ha habido algún detalle pequeño que te haya gustado?', 'Hoy el archivo propone una misión diminuta: ponerle título al día. El mío sería «Una galleta entre dos papeles». ¿Y el tuyo?'],
      default: ['Te leo, Patita. En mi escritorio caben asuntos de todos los tamaños. ¿Qué parte te apetece contarme un poquito más?', 'Dejamos una página nueva para eso, Patita. ¿Quieres seguir charlando, abrir un expediente bonito o escuchar un cuento?']
    },
    mimosuga: {
      hello: ['Hola, mi Patita. Esta abuela tortuga ya ha acercado una silla. Cuéntame, ¿cómo viene tu día?', 'Aquí estás, Patita. Tenemos tiempo para una historia y para sus silencios. ¿Por dónde empezamos?'],
      tired: ['Ay, Patita. Hay días que parecen llevar un caparazón prestado. Aquí podemos ir despacito: una frase, luego otra. ¿Qué te ha dejado tan cansada?', 'Ven a este rinconcito del cuento, Patita. No hace falta acabar todas las cosas para merecer un momento amable. Te presto una de mis historias si te apetece.'],
      sad: ['Ay, Patita, siento que hoy estés así. Te mando un abrazo de abuela tortuga, de los imaginarios y mulliditos. ¿Quieres contarme qué ha pasado?', 'A veces el corazón necesita una silla y alguien que escuche, Patita. Podemos dejar espacio a la tristeza sin buscarle enseguida un final bonito.'],
      thanks: ['De nada, Patita. Las palabras cariñosas son como los botones: con poquitas sujetan muchas cosas.'],
      gift: ['Mi detalle favorito, Patita, es una nota que diga algo concreto y verdadero: «Me hizo feliz cuando…». ¿Qué recuerdo te gustaría regalar?', 'Yo prepararía una cajita de recuerdos: una frase, un dibujo y el nombre de un día bonito. Lo precioso puede caber en un bolsillo.'],
      everyday: ['Cuéntame una cosa chiquitita de hoy, Patita. Puede ser el color del cielo o una frase que te hizo sonreír. Las abuelas sabemos empezar cuentos con muy poco.', 'El día de hoy todavía no tiene título en mi cuaderno. ¿Lo llamamos «Sin prisa», «Una pequeña sorpresa» o inventamos otro?'],
      default: ['Te escucho, Patita. Puedes seguir por ahí, sin ordenar mucho las palabras. ¿Qué es lo que más te ronda?', 'Vamos despacito, Patita. ¿Te apetece contarme un poco más o prefieres que saque un cuento de mi bolsillo?']
    },
    salchicher: {
      hello: ['¡Hola, Patita! Gafitas en su sitio, orejitas atentas y consulta de mimos abierta. Este perrito te escucha: ¿cómo viene tu día?', 'Adelante, Patita. Me acomodo las gafitas y te acerco una silla. En la consulta de mimos podemos ir despacito. ¿Qué te apetece contarme?'],
      tired: ['Me acomodo las gafas, Patita. Para esta pausa de cuento propongo elegir una escena: una ventana con lluvia, un jardín tranquilo o una biblioteca diminuta. ¿Dónde nos sentamos?', 'Hoy podemos bajar el volumen de nuestro cuento, Patita. Sin grandes hazañas: solo una conversación tranquila. ¿Quieres una historia o prefieres contarme tu día?'],
      sad: ['Siento que hoy te pese el día, Patita. Dejo el cuaderno a un lado para escucharte. ¿Te gustaría contar qué ha pasado?', 'No tienes que traer una sonrisa puesta, Patita. Podemos hablar de lo que sientes o buscar una historia amable para acompañar este rato.'],
      thanks: ['¡Gracias a ti, Patita! Apunto en el cuaderno: «Un momento amable compartido». Es una buena página para hoy.'],
      gift: ['Tengo una idea de detalle bonito, Patita: una tarjeta con tres pequeñas cosas que admiras de alguien. Sin palabras enormes, solo cosas de verdad.', 'Un regalo curioso: un vale dibujado para una tarde de conversación, una peli o una merienda. ¿Qué plan le haría ilusión a esa persona?'],
      everyday: ['Abramos el cuaderno de pequeñas alegrías, Patita. ¿Qué merece hoy una estrellita: haber empezado algo, haber terminado algo o haber pedido ayuda?', 'Hoy propongo celebrar una cosa que normalmente pasa desapercibida. Puede ser tan pequeña como encontrar algo que dabas por perdido. ¿Se te ocurre una?'],
      default: ['Te leo, Patita. ¿Quieres contarme un poco más, inventar una pausa bonita o celebrar algo pequeño del día?', 'Me ajusto las gafas y te escucho, Patita. Podemos seguir charlando o abrir el cuaderno de historias. ¿Qué te apetece?']
    },
    vaca: {
      hello: ['¡Tolón, tolón, Patita! Un poquito de purpurina iridiscente y ya tenemos saludo. Hay una estrella de papel esperando un nombre bonito. ¿Cómo llamamos a tu día?', 'Hola, Patita. Las lucecitas están encendidas en nuestro cuento. Aquí también celebramos las alegrías de cualquier martes.'],
      tired: ['Hoy puede ser una Navidad pequeñita, Patita: una sola luz en una ventana y ningún gran preparativo. ¿Qué escena tranquila te gustaría imaginar?', 'Ven al rincón de las luces suaves, Patita. Nuestro cuento de hoy puede caminar muy despacio. ¿Te cuento el del deseo que no necesitaba un lazo?'],
      sad: ['Te acompaño un ratito con palabras, Patita. Las lucecitas también pueden estar encendidas en un día triste. ¿Quieres contarme qué te pasa?', 'No todos los días suenan a cascabeles, Patita. Aquí hay sitio para cómo te sientes hoy. Podemos hablar o imaginar una escena tranquila.'],
      thanks: ['Muuuuchas gracias a ti, Patita. Si esta charla fuera una estrella de papel, le pondríamos un hilo dorado.'],
      gift: ['Podemos imaginar un deseo, Patita. No puedo prometer regalos ni hacer que se cumpla, pero sí ayudarte a ponerlo en palabras. ¿Qué te gustaría escribir?', 'Un deseo no siempre cabe en una caja, Patita. Puede ser una tarde compartida o una conversación pendiente. ¿Qué forma tiene el tuyo?'],
      everyday: ['Imaginemos una Navidad de bolsillo, Patita: una estrella, una mesa y alguien a quien acercar una silla. ¿Qué añadirías tú?', 'En nuestro cuento las luces siguen encendidas todo el año. ¿Qué detalle pequeño de hoy te gustaría convertir en una estrella de papel?'],
      default: ['Te escucho, Patita. Podemos darle palabras a un deseo, imaginar una Navidad bonita o abrir un cuento. ¿Por dónde seguimos?', 'Dejamos una lucecita junto a esa idea, Patita. ¿Te apetece contarme algo más sobre ella?']
    },
    dulcimiel: {
      hello: ['Hola, Patita. Me acomodo el pañuelo turquesa y abro mi cuaderno. Mi prima, la Vaca Mágica, dice que las mejores aventuras empiezan con una idea pequeña. ¿Inventamos una?', 'Qué gusto verte, Patita. Soy una vaca exploradora de sabores de cuento: hoy podemos imaginar uno tan tranquilo como una tarde junto a la ventana.'],
      tired: ['Entonces nuestra aventura de hoy puede llamarse «Poquito a poquito», Patita. Me siento a tu lado en el cuento, con mi pañuelo turquesa y el cuaderno abierto. ¿Qué escena tranquila dibujamos?', 'Hoy la dulzura puede ser una frase breve, Patita: «No todo tiene que caber en este día». Mis exploraciones también tienen tardes sin prisa. ¿Quieres que inventemos una?'],
      sad: ['Siento que hoy estés triste, Patita. No hace falta endulzarlo todo. Podemos darle espacio a lo que sientes y hablar de ello, si te apetece.', 'Hay palabras que no arreglan un día, pero pueden acompañar un ratito: te leo, Patita. ¿Qué te gustaría contar?'],
      thanks: ['Gracias a ti, Patita. Guardo estas palabras en mi cuaderno, junto a los sabores de cuento que todavía no tienen nombre.'],
      gift: ['En nuestros cuentos, visito una vez por Navidad con helados y «leche mágica», que es horchata, Patita. Mi prima es la Vaca Mágica. Aquí podemos imaginar cómo sería esa escena: ¿lucecitas en la ventana o estrellas de papel?', 'Mi Navidad de cuento tiene un pañuelo turquesa, helados y «leche mágica», que es horchata. No puedo prometerte entregas, Patita, pero sí inventar contigo una historia de aquella visita anual.'],
      everyday: ['Propongo tres nombres para tu día, Patita: «Una cucharadita de calma», «Ventanas abiertas» o «Lo bonito todavía cabe». Los anoto con cuidado en mi cuaderno. ¿Cuál se parece más al tuyo?', 'Como exploradora de sabores de cuento, empiezo por observar, Patita: un color, una palabra o una pequeña alegría. ¿Cuál llevamos hoy a nuestra aventura imaginaria?'],
      flavor: ['Imaginemos un helado que solo existe en un cuento, Patita: «Tarde de nubes turquesa». Cada cucharada inventada abre una ventanita a un cielo distinto. Me ajusto el pañuelo y lo dibujo en mi cuaderno. ¿Qué nombre tendría tu sabor imaginario?', 'En mi cuaderno de cuentos aparece un sabor nuevo, Patita: «La primera estrella». No tiene receta: sabe, en nuestra imaginación, a abrir una carta bonita. ¿Qué pequeño recuerdo convertirías tú en un sabor de ficción?'],
      identity: ['Soy Dulcimiel, Patita: una vaca tranquila, creativa y exploradora de sabores, con mi pañuelo turquesa. La Vaca Mágica es mi prima. En nuestros cuentos hago una visita por Navidad con helados y «leche mágica», que es horchata.'],
      default: ['Te leo, Patita. Me acomodo el pañuelo turquesa y dejo una página libre. ¿Seguimos con esa idea o inventamos un sabor que solo exista en un cuento?', 'Podemos darle un título a eso, Patita. Mi cuaderno de exploradora tiene espacio para las pequeñas ideas. ¿Me cuentas un poquito más?']
    }
  };

  function normalize(value) {
    return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  }

  function careResponse(characterId, input, history) {
    // Remove explicit symptom denials, while preserving separate affirmative clauses.
    const signals = input
      .replace(/\bno (?:tengo|siento|hay|presento) (?:ningun[a]? )?(?:fiebre|dolor(?: (?:fuerte|intenso|insoportable))?|dificultad (?:para|al) respirar|sangre (?:en (?:las )?heces|al vomitar))\b/g, '')
      .replace(/\bno (?:he vomitado|vomito) sangre\b/g, '')
      .replace(/\bno (?:me he desmayado|me desmayo|se me (?:ha )?hinchado (?:la lengua|los labios))\b/g, '');

    const breathingEmergency = /\b(?:no pued[oe] respirar|me (?:cuesta respirar|ahogo)|dificultad (?:para|al) respirar)\b/.test(signals);
    const bloodEmergency = /\b(?:(?:vomito|vomitando|vomitado) sangre|sangre (?:al vomitar|en (?:mis |las )?(?:heces|deposiciones)))\b/.test(signals);
    const collapseEmergency = /\b(?:me (?:he desmayado|desmayo)|se ha desmayado|he tenido un desmayo)\b/.test(signals);
    const swellingEmergency = /\b(?:hinchazon (?:en|de) (?:la lengua|los labios)|(?:lengua|labios) (?:muy )?hinchad[ao]s?|se me (?:ha |han )?hinchado (?:la lengua|los labios))\b/.test(signals);
    const poisoningEmergency = /\b(?:intoxicacion|me he intoxicado|he (?:tomado|bebido|ingerido) (?:veneno|lejia|un producto de limpieza))\b/.test(signals);
    const severePain = /\b(?:dolor (?:muy )?(?:fuerte|intenso|insoportable)|(?:me )?duele[^.!?;]{0,45}\b(?:muchisimo|mucho|muy fuerte|intensamente|demasiado))\b/.test(signals);

    if (breathingEmergency || bloodEmergency || collapseEmergency || swellingEmergency || poisoningEmergency || severePain) {
      return 'Patita, lo que describes necesita ayuda médica urgente. Llama al 112 ahora o pide a alguien que llame y se quede contigo. No esperes a seguir esta conversación.';
    }

    const priorMessages = Array.isArray(history) ? history.filter(function (item) { return item && item.role === 'user'; }) : [];
    const previousInput = priorMessages.length ? normalize(priorMessages[priorMessages.length - 1].text) : '';
    const painContext = /\b(?:dolor|duele|molestia|molestias|tripota|tripa|barriga|estomago)\b/.test(signals + ' ' + previousInput);
    const persistentSymptoms = /\b(?:persiste|persistente|empeora|empeorando|va a peor|no se me (?:pasa|quita)|no se (?:pasa|quita)|llevo (?:varios|muchos|dos|tres|cuatro|cinco|\d+) dias|desde hace (?:varios|muchos|dos|tres|cuatro|cinco|\d+) dias)\b/.test(signals);
    if (painContext && persistentSymptoms) {
      return 'Patita, si esa molestia sigue o está empeorando, es momento de consultarlo con un profesional sanitario. No hace falta aguantarla ni intentar adivinar qué es. ¿Puedes pedir que te valoren?';
    }

    if (/\b(?:medicamentos?|pastillas?|dosis|diagnostico|diagnosticar|antibioticos?|tratamiento)\b/.test(input) || /\b(?:que enfermedad tengo|que tengo que tomar|necesito (?:un )?medico)\b/.test(input)) {
      return 'Eso hay que consultarlo con un profesional, Patita. No voy a adivinar un diagnóstico ni decirte qué medicamento o dosis tomar. Si ya tienes una pauta, confirma cualquier duda con tu médico o farmacéutico. Yo puedo ayudarte a poner en palabras lo que quieres preguntar.';
    }

    if (/\bjalea real\b/.test(input)) {
      return 'Para nuestro cuento, la cambio por jalea de nubes imaginaria, Patita. Es un ingrediente de cuento, no un suplemento ni algo para tratar el malestar: solo se sirve en las páginas de nuestro cuaderno. Le pongo una etiqueta turquesa y un dibujito de nube. ¿Qué nombre le damos?';
    }

    const tummyDiscomfort = /\b(?:tripa|tripota|barriga|barriguita|estomago)\b/.test(signals) && /\b(?:duele|dolor|molestia|molestias|revuelta|revuelto|mal)\b/.test(signals);
    if (tummyDiscomfort && characterId === 'salchicher') {
      return 'Ay, esa tripota, Patita. Hoy toca bajar el ritmo: un ratito tranquila, sorbitos de agua y, si te apetece, un abrazo de perro de los que no aprietan. En mi cuaderno añado dos cucharadas imaginarias de mojo de oso y un pellizquito de paciencia. ¿Ha empezado hace poquito?';
    }
    if (tummyDiscomfort) {
      return 'Ay, esa tripota, Patita. Podemos ir despacito: un ratito tranquila y sorbitos de agua. Te acompaño con unas palabras suaves. ¿Ha empezado hace poquito?';
    }

    if (/\bmojo de oso\b/.test(input)) {
      return '¡Mojo de oso imaginario, Patita! Lo dibujo en el cuaderno con dos cucharadas de ternura y un pellizquito de paciencia. Es un ingrediente de cuento: no se toma ni cura nada. ¿Lo guardamos en un tarrito con estrellas?';
    }
    if (characterId === 'salchicher' && /\b(?:autocuidado|cuidarme|habitos|cuidado cotidiano)\b/.test(input)) {
      return 'Me ajusto las gafitas, Patita. Para cuidarte en lo cotidiano podemos empezar por cosas sencillas: descansar, beber agua con normalidad, comer de forma variada y buscar un ratito tranquilo. Sin convertirlo en una lista de deberes. ¿Qué pequeño cuidado te apetece hoy?';
    }
    if (characterId === 'salchicher' && /^no tengo fiebre[.!\s]*$/.test(input)) {
      return 'Te escucho, Patita. Me acomodo las gafitas y lo anoto, sin sacar conclusiones solo por eso. ¿Cómo te encuentras y qué te apetece contarme?';
    }
    return null;
  }

  function reply(id, text, history) {
    const characterId = Object.prototype.hasOwnProperty.call(characters, id) ? id : 'castori';
    const input = normalize(text);
    const turns = Array.isArray(history) ? history.filter(function (item) { return item && (item.role === 'assistant' || item.role === 'animal'); }).length : 0;
    let intent = 'default';

    if (!input) return characters[characterId].greeting;

    const care = careResponse(characterId, input, history);
    if (care) return care;

    if (characterId === 'vaca' && /\b(profecia|profecias|pista|pistas|campanilla|venir|vienes|llegas|llegada|visita|secreto)\b/.test(input)) {
      const prophecies = [
        'Muuu… mi campanilla ha soñado que una estrella se enganchaba en un lazo y se negaba a soltarlo. «Ese lazo guarda algo», decía. Y yo, que soy muuuuy discreta, he cerrado el cuaderno antes de que leyera tu nombre. ¿Qué crees que habrá visto? ✧\n\nProfecía de ejemplo del boceto; no anuncia una visita real.',
        'Tolón… Patita, en esta profecía de ejemplo hay un paquetito tan impaciente que se ha puesto los zapatos del revés. No te digo más, que luego mi campanilla me llama bocazas. ¿Tú crees que sabe esperar? ✧\n\nEs una escena del boceto, sin fecha ni entrega real.'
      ];
      return prophecies[turns % prophecies.length];
    }

    if (characterId === 'dulcimiel' && /\b(prima|panuelo|animal|eres)\b/.test(input)) return voice.dulcimiel.identity[0];
    if (characterId === 'dulcimiel' && /\b(horchata|leche)\b/.test(input)) return voice.dulcimiel.gift[0];
    if (characterId === 'dulcimiel' && /\b(sabor|sabores|helado|helados)\b/.test(input)) return voice.dulcimiel.flavor[turns % voice.dulcimiel.flavor.length];

    if (/\b(cuento|cuentos|historia|historias|relato|relatos)\b/.test(input)) {
      const storyIndex = characterId === 'mimosuga' ? 0 : characterId === 'vaca' ? 2 : characterId === 'castori' ? 1 : turns % stories.length;
      return stories[storyIndex].title + '\n\n' + stories[storyIndex].body;
    }
    if (/\b(triste|tristeza|llorar|llorando|sola|solo|soledad|mal|abrazo|abrazos|animo|preocupada|preocupado|miedo|angustia)\b/.test(input)) intent = 'sad';
    else if (/\b(cansada|cansado|cansancio|agotada|agotado|pausa|descanso|descansar|estres|estresada|estresado)\b/.test(input)) intent = 'tired';
    else if (/\b(regalo|regalos|regalar|deseo|deseos|pedir|navidad|navidena|navideno|reyes|cumpleanos|ilusion)\b/.test(input)) intent = 'gift';
    else if (/\b(gracias|agradezco|agradecida|agradecido)\b/.test(input)) intent = 'thanks';
    else if (/\b(hola|holi|buenas|saludos|hey)\b/.test(input) || /buenos dias|buenas tardes|buenas noches/.test(input)) intent = 'hello';
    else if (/\b(dia|bonito|bonita|bonitas|bonitos|alegria|feliz|contenta|contento|celebrar|expediente|idea|dulce|pequeno|pequena|nombre)\b/.test(input)) intent = 'everyday';

    const options = voice[characterId][intent];
    return options[turns % options.length];
  }

  window.CastoriDialogue = { characters: characters, reply: reply, stories: stories };
}());
