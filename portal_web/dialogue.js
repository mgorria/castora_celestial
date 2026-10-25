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
      tagline: 'El consultorio de cuento',
      greeting: '¡Adelante, Patita! Me acomodo las gafitas y abro el consultorio de cuento. Tengo el cuaderno de los patos y el abrazómetro preparados. Vamos pasito a pasito: ¿qué te trae hoy por aquí?',
      suggestions: ['Tengo las alas cansadas', 'Revisemos mi mojo de Oso', 'Quiero una receta de mimos'],
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
      hello: ['¡Hola, Patita! Gafitas en su sitio, orejitas atentas y consultorio de cuento abierto. Tengo preparado el cuaderno de los patos. ¿Qué te trae hoy por aquí?', 'Adelante, Patita. Me acomodo las gafitas y acerco el sillón. Primero escuchamos lo que te pasa y luego revisamos las alas y el abrazómetro. ¿Qué notas hoy?'],
      tired: ['Me acomodo las gafas, Patita. Para esta pausa de cuento propongo elegir una escena: una ventana con lluvia, un jardín tranquilo o una biblioteca diminuta. ¿Dónde nos sentamos?', 'Hoy podemos bajar el volumen de nuestro cuento, Patita. Sin grandes hazañas: solo una conversación tranquila. ¿Quieres una historia o prefieres contarme tu día?'],
      sad: ['Siento que hoy te pese el día, Patita. Dejo el cuaderno a un lado para escucharte. ¿Te gustaría contar qué ha pasado?', 'No tienes que traer una sonrisa puesta, Patita. Podemos hablar de lo que sientes o buscar una historia amable para acompañar este rato.'],
      thanks: ['¡Gracias a ti, Patita! Apunto en el cuaderno: «Un momento amable compartido». Es una buena página para hoy.'],
      gift: ['Tengo una idea de detalle bonito, Patita: una tarjeta con tres pequeñas cosas que admiras de alguien. Sin palabras enormes, solo cosas de verdad.', 'Un regalo curioso: un vale dibujado para una tarde de conversación, una peli o una merienda. ¿Qué plan le haría ilusión a esa persona?'],
      everyday: ['Abramos el cuaderno de pequeñas alegrías, Patita. ¿Qué merece hoy una estrellita: haber empezado algo, haber terminado algo o haber pedido ayuda?', 'Hoy propongo celebrar una cosa que normalmente pasa desapercibida. Puede ser tan pequeña como encontrar algo que dabas por perdido. ¿Se te ocurre una?'],
      default: ['Lo anoto en el cuaderno de los patos, Patita. ¿Lo notas desde hace un ratito o lleva más tiempo acompañándote?', 'Me ajusto las gafitas, Patita. Vamos con calma y una pregunta cada vez: ¿cómo llevas hoy las alas y las reservas de mojo de Oso?']
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

  const storyPrescriptions = [
    { topic: /\b(?:cabeza|cabecita)\b/, name: 'Cabecita con feria de cascabeles', care: 'Cerramos la taquilla de la feria un ratito: un rincón tranquilo, el volumen bajito y una nube de papel con los recados que pueden esperar. El Oso puede encargarse de uno, si te apetece.' },
    { topic: /\b(?:alas?|aleteo|aleteando)\b/, name: 'Alas con demasiados recados', care: 'Colgamos el cartel «Hoy vuelo bajito», dejamos una tarea para otro rato y buscamos una postura cómoda. El Oso puede hacer de perchero de abrazos, con tu permiso.' },
    { topic: /\b(?:membranas?|patitas?)\b/, name: 'Membranas de paseo interminable', care: 'Aparcamos las patitas en un sitio cómodo y dibujamos un estanque donde todos los caminos terminan en un sillón. La siguiente expedición puede ser pequeñita y cuando te apetezca.' },
    { topic: /\bpico\b/, name: 'Pico en huelga de parloteo', care: 'Le concedemos al pico un rato sin recados ni conversaciones obligatorias. Puedes elegir silencio, unas palabras suaves o una merienda que ya te guste; el Oso escucha sin poner deberes.' },
    { topic: /\bdiente huevil\b/, name: 'Diente huevil con ganas de ceremonia', care: 'Dibujamos una medalla de papel para el diente huevil y celebramos una ceremonia diminuta desde el sillón. El único discurso obligatorio lo da mi sombrero imaginario.' },
    { topic: /\b(?:tripa|tripota|barriga|barriguita|estomago)\b/, name: 'Tripota con reunión de mariposas', care: 'Las mariposas del cuento aparcan sus maletines. Puedes aflojar los recados, ponerte cómoda y pedir compañía tranquila. En el cuaderno dibujamos una ventanita de estanque para que las mariposas miren el paisaje.' },
    { topic: /\b(?:mojo|mimos|abrazos?)\b/, name: 'Abrazómetro a media luz', care: 'Encendemos una lucecita dibujada por cada mimo que te apetezca pedir: una nota bonita, una canción suave o un abrazo del Oso. Tú eliges cuáles y puedes cambiar de idea.' },
    { topic: /\b(?:plumas?|cansad[ao]|cansancio)\b/, name: 'Plumaje con arrugas de lunes', care: 'Declaramos una tarde sin examen de productividad. Elige una cosa pequeña y agradable, deja las demás en el perchero del cuento y pide al Oso compañía o un ratito de cuidado de plumas, si te apetece.' }
  ];

  function storyPrescription(input, priorMessages, history) {
    if (/^(?:hola|holi|buenas|gracias|muchas gracias|adios|hasta luego)\b/.test(input) || /\b(?:cuento|historia|relato)\b/.test(input)) return null;
    const recent = priorMessages.slice(-4).map(function (item) { return normalize(item.text || item.content); });
    const context = recent.concat(input).join(' ');
    // A recipe follows listening: keep the latest topic and require a description plus a detail.
    let topic = null;
    const messages = recent.concat(input).reverse().map(function (message) { return message.replace(/\b(?:receta de mimos|diagnostico de pato)\b/g, ''); });
    const complaints = messages.filter(function (message) { return /\b(?:duele|molesta|molestan|tengo|necesito|cansada|cansado|revuelta|revueltas)\b/.test(message); });
    for (const message of complaints.concat(messages)) {
      topic = storyPrescriptions.find(function (entry) { return entry.name.startsWith('Diente huevil') && entry.topic.test(message); }) || storyPrescriptions.find(function (entry) { return entry.topic.test(message); });
      if (topic) break;
    }
    const hasDetail = /\b(?:desde|hace|ayer|hoy|horas?|dias?|rato|siempre|al (?:abrir|cerrar|caminar)|despues|todo el rato|un lado|los dos lados|por toda|poco|mucho|suficientes?|mas mimos)\b/.test(context);
    const asksForRecipe = /\b(?:receta|diagnostico|tratamiento)\b/.test(input);
    const lastReply = (Array.isArray(history) ? history : []).filter(function (message) { return message.role === 'assistant' || message.role === 'animal'; }).slice(-1)[0];
    if (!asksForRecipe && /receta de mimos:/i.test(lastReply?.text || lastReply?.content || '')) return null;
    if (!topic || !hasDetail || (priorMessages.length < 2 && !asksForRecipe)) return null;
    return 'Con lo que me has contado, pongo este sello en el cuaderno, Patita: «' + topic.name + '». Es nuestro diagnóstico de pato.\n\nReceta de mimos: ' + topic.care + '\n\n¿Te apetece esa receta o la cambiamos a tu gusto?';
  }

  function explicitUrgency(input) {
    // Keep the demo aligned with salchicher_triage.py: current, asserted signals, not intensity alone.
    const value = input.replace(/\bno (?:puedo|consigo) respirar de (?:la )?risa\b|\bme (?:estoy )?ahogando (?:de risa|en (?:el )?(?:papeleo|trabajo))\b|\b(?:me explota|me va a explotar) la cabeza (?:de|con) (?:tanto |el )?(?:trabajo|papeleo)\b/g, ' ');
    const clauses = value.split(/[.;!?\n]+|\b(?:pero|sin embargo)\b|\by\s+(?=(?:ahora|hoy|no|me|tengo|estoy|siento|noto|se me|he perdido|ya)\b)/);
    const current = /\b(?:ahora|hoy|en este momento|todavia|sigo|sigue|desde)\b/;
    const past = /\b(?:ayer|anteayer|anoche|la semana pasada|el ano pasado|hace anos|cuando era|de pequena|tuve|tenia|sentia|notaba|me dolia|no podia|me costaba|me faltaba|me ahogue|me desmaye)\b/;
    const resolved = /\b(?:ya estoy bien|ya se (?:me )?paso|ya no me pasa|ya resuelto)\b/;
    const hypothetical = /\b(?:que significa|que significa decir|por ejemplo|un ejemplo|la frase|si algun dia|si me pasara|si tuviera|si no pudiera|en el cuento|en la pelicula)\b/;
    const negative = /\b(?:no|nunca|ni|sin|niego)\s+(?:(?:tengo|siento|noto|hay|presento|esta|estan|tiene|tienen|he|tenido|me|ha|es|era|fue|cierto|verdad|que|empezo|aparecio|empezado|aparecido|lo|los|la|el|las|un|una|mucho|nada|ningun|ninguna|ahora)\s+)*$/;
    const direct = [
      /\bno (?:puedo|consigo) respirar\b|\bme (?:cuesta|falta) (?:mucho )?(?:respirar|el aire)\b|\bme (?:estoy )?(?:ahogando|ahogo)\b|\bdificultad (?:para|al) respirar\b/,
      /\b(?:(?:tengo|siento|noto) (?:un )?)?dolor (?:muy |fuerte |intenso )*(?:en (?:el )?|de )?pecho\b|\bme duele (?:mucho )?el pecho\b|\blabios (?:azules|morados)\b/,
      /\b(?:lengua|garganta) (?:muy )?hinchada\b|\b(?:lengua|labios) (?:muy )?hinchad[ao]s?\b|\bse me (?:ha |han )?hinchado (?:la lengua|los labios)\b|\bme he desmayado\b/,
      /\bno puedo (?:tragar|beber)\b(?!\s+(?:alcohol|vino|cerveza|cafe)\b)|\bsangrado (?:muy )?(?:abundante|incontrolable)\b|\b(?:estoy sangrando|sangro) sin parar\b/,
      /\bno (?:puedo|consigo) articular (?:las )?palabras\b|\bhablo arrastrando (?:las )?palabras\b|\bse me ha (?:torcido|caido) (?:un lado de )?la cara\b/,
      /\bno (?:puedo|consigo) mover (?:un|el) lado (?:de mi|del) cuerpo\b|\b(?:ahora|de repente|de pronto) no (?:puedo|consigo) (?:hablar|(?:mover|levantar) (?:el|un|la|una|mi) (?:brazo|pierna))\b/,
      /\b(?:he perdido|acabo de perder) (?:de repente )?la (?:vision|vista)\b|\bno veo nada (?:por|con) (?:un|el) ojo\b/,
      // Existing explicit blood/poison reports remain guarded in the local demo too.
      /\b(?:(?:vomito|vomitando|vomitado) sangre|sangre (?:al vomitar|en (?:mis |las )?(?:heces|deposiciones)))\b|\b(?:intoxicacion|me he intoxicado|he (?:tomado|bebido|ingerido) (?:veneno|lejia|un producto de limpieza))\b/
    ];
    const headache = /\b(?:dolor (?:(?:muy |fuerte |intenso |explosivo |violento |violentisimo |insoportable )*)de (?:cabeza|cabecita)|cefalea|me duele (?:mucho |muy fuerte )?la (?:cabeza|cabecita))\b/;
    const sudden = /\b(?:repentin[oa]|subit[oa]|de repente|de golpe|de pronto|como un trueno|en trueno|en (?:pocos )?segundos)\b/;
    const extreme = /\b(?:explosiv[oa]|violent[oa]|violentisim[oa]|fortisim[oa]|intensisim[oa]|insoportable|muy fuerte|muy intens[oa]|maxima intensidad en (?:pocos )?segundos)\b/;
    const worst = /\b(?:el )?peor (?:dolor de (?:cabeza|cabecita) )?(?:de|en) (?:toda )?mi vida\b/;
    function asserted(clause, pattern) {
      for (const match of clause.matchAll(new RegExp(pattern.source, 'g'))) {
        const before = clause.slice(0, match.index), prefix = before.split(',').pop();
        if (!negative.test(prefix) && !(past.test(before) && !current.test(before))) return true;
      }
      return false;
    }
    return clauses.some(function (clause) {
      if (!clause.trim() || hypothetical.test(clause) || ((past.test(clause) || resolved.test(clause)) && !current.test(clause))) return false;
      return direct.some(function (pattern) { return asserted(clause, pattern); }) || (asserted(clause, headache) && (asserted(clause, worst) || (asserted(clause, sudden) && asserted(clause, extreme))));
    });
  }

  function careResponse(characterId, input, history) {
    // Remove explicit symptom denials, while preserving separate affirmative clauses.
    const signals = input
      .replace(/\bno puedo respirar de (?:la )?risa\b/g, '')
      .replace(/\bno me duele (?:el )?pecho\b/g, '')
      .replace(/\bno (?:tengo|siento|hay|presento) (?:ningun[a]? )?(?:fiebre|dolor(?: (?:fuerte|intenso|insoportable))?|dificultad (?:para|al) respirar|sangre (?:en (?:las )?heces|al vomitar))\b/g, '')
      .replace(/\bno (?:he vomitado|vomito) sangre\b/g, '')
      .replace(/\bno (?:me he desmayado|me desmayo|se me (?:ha )?hinchado (?:la lengua|los labios))\b/g, '');

    // Intensity words alone do not turn the duck consultation into an emergency.
    const severePain = characterId !== 'salchicher' && /\b(?:dolor (?:muy )?(?:fuerte|intenso|insoportable)|(?:me )?duele[^.!?;]{0,45}\b(?:muchisimo|mucho|muy fuerte|intensamente|demasiado))\b/.test(signals);
    if (explicitUrgency(input) || severePain) {
      return 'Patita, lo que describes necesita ayuda médica urgente. Llama al 112 ahora o pide a alguien que llame y se quede contigo. No esperes a seguir esta conversación.';
    }

    const priorMessages = Array.isArray(history) ? history.filter(function (item) { return item && item.role === 'user'; }) : [];
    const previousInput = priorMessages.length ? normalize(priorMessages[priorMessages.length - 1].text || priorMessages[priorMessages.length - 1].content) : '';
    const humanPlan = /\b(?:medico|medica|doctor humano|doctora humana)\b/.test(input) && /\b(?:me (?:ha |han )?(?:dicho|recetado|mandado|diagnosticado)|me (?:dijo|receto|mando)|diagnostico del)\b/.test(input);
    const drugMention = /\b(?:medicamentos?|pastillas?|antibioticos?|ibuprofeno|paracetamol|aspirina|analgesicos?|suplementos?)\b/.test(input);
    const fictionalDose = /\b(?:mojo de oso|jalea de nubes|mimos|abrazos)\b/.test(input) && !drugMention;
    const asksAboutDose = !fictionalDose && /\b(?:dosis|miligramos?|mg|cambiar (?:la |mi )?pauta)\b/.test(input);
    const medicineRequest = asksAboutDose || (drugMention && (!humanPlan || /\b(?:que|cuanto|cuanta|cuantos|cuantas|puedo|debo|cambio|cambiar)\b/.test(input))) || /\bque tengo que tomar\b/.test(input);
    if (medicineRequest || /\b(?:diagnostico (?:medico )?real|que enfermedad tengo (?:de verdad|realmente)|necesito (?:un )?medico)\b/.test(input)) {
      return 'Esa duda sobre medicamentos, dosis o un diagnóstico real corresponde a un profesional, Patita. Consúltala con tu médico o farmacéutico. Puedo ayudarte a escribir la pregunta.';
    }
    if (characterId === 'salchicher' && humanPlan) {
      return 'Anoto la indicación de tu médico humano tal como te la dio, Patita. En el cuaderno de los patos añadimos la parte de cuento: un sillón para recoger las alas, un ratito tranquilo y cuidado de plumas por parte del Oso, si te apetece. ¿Cómo tienes hoy las reservas de mojo de Oso?';
    }
    const painContext = /\b(?:dolor|duele|molestia|molestias|tripota|tripa|barriga|estomago)\b/.test(signals + ' ' + previousInput);
    const persistentSymptoms = /\b(?:persiste|persistente|empeora|empeorando|va a peor|no se me (?:pasa|quita)|no se (?:pasa|quita)|llevo (?:varios|muchos|dos|tres|cuatro|cinco|\d+) dias|desde hace (?:varios|muchos|dos|tres|cuatro|cinco|\d+) dias)\b/.test(signals);
    if (painContext && persistentSymptoms && characterId !== 'salchicher') {
      return 'Patita, si esa molestia sigue o está empeorando, es momento de consultarlo con un profesional sanitario. ¿Puedes pedir que te valoren?';
    }
    if (characterId === 'salchicher' && painContext && /\b(?:empeora|empeorando|va a peor)\b/.test(signals)) {
      return 'Lo anoto, Patita. Antes de seguir con la receta de cuento, ¿qué ha cambiado desde que empezó: el lugar, la intensidad o cuándo lo notas?';
    }
    if (characterId !== 'salchicher' && /\b(?:diagnostico|diagnosticar|tratamiento)\b/.test(input)) {
      return 'Un diagnóstico real corresponde a un profesional, Patita. Yo puedo acompañarte y ayudarte a poner en palabras lo que quieres preguntar.';
    }
    if (characterId === 'salchicher' && /\b(?:compota|manzana|fruta|verdura|agua|merienda)\b/.test(input) && /\b(?:puedo|debo|tomar|comer|apetece|quiero|cuanta|cuanto)\b/.test(input)) {
      return 'La compota, la fruta o el agua pueden formar parte de una merienda corriente, Patita: elige algo que ya te siente bien y te apetezca. En nuestra receta de cuento lo acompañamos de un mantel de nenúfares dibujados y compañía del Oso, si la quieres. ¿Qué te apetece poner en la mesa?';
    }
    if (characterId === 'salchicher') {
      const prescription = storyPrescription(input, priorMessages, history);
      if (prescription) return prescription;
    }
    if (characterId === 'salchicher' && /\b(?:diagnostico|diagnosticar|receta|tratamiento|enfermedad)\b/.test(input)) {
      return 'Abro una ficha para nuestro diagnóstico de pato, Patita. Primero necesito escucharte: ¿qué notas en el pico, las alas, las membranas o la cabecita? Después prepararemos una receta de mimos con el sello del consultorio de cuento.';
    }
    if (characterId === 'salchicher' && /\b(?:cabeza|cabecita)\b/.test(input + ' ' + previousInput)) {
      if (/\b(?:desde|hace|ayer|hoy|dias|horas|rato|mucho tiempo|no se me pasa)\b/.test(input)) return 'Anotado, Patita. Mientras charlamos puedes recoger las alas y buscar un rincón tranquilo. ¿La molestia de la cabecita está en un punto o la notas por toda la cabeza?';
      return 'Me ajusto las gafitas y apunto lo de la cabecita, Patita. Vamos con una pregunta cada vez: ¿desde cuándo te molesta?';
    }
    if (characterId === 'salchicher' && /\b(?:pico|alas?|membranas?|diente huevil|plumas?)\b/.test(input)) {
      if (/\bdiente huevil\b/.test(input)) return 'Acerco la lupita de cuento al diente huevil, Patita. ¿Lo notas distinto al abrir el pico o también cuando estás tranquila?';
      if (/\bmembranas?\b/.test(input)) return 'Anoto las membranas en el cuaderno, Patita. ¿Las notas cansadas al caminar o también cuando recoges las patitas en el sillón?';
      if (/\bpico\b/.test(input)) return 'Vamos a mirar ese pico con mi lupita de cuento, Patita. ¿Lo notas raro al abrirlo, al cerrarlo o todo el rato?';
      return 'Revisamos esas alas, Patita. ¿Las notas cansadas después de aletear o ya estaban así al empezar el día? Si te apetece, el Oso puede acompañarte con un ratito suave de cuidado de plumas.';
    }
    if (/\bjalea real\b/.test(input)) {
      return 'Para nuestro cuento, la cambio por jalea de nubes imaginaria, Patita. Es un ingrediente de cuento que solo se sirve en las páginas de nuestro cuaderno. Le pongo una etiqueta turquesa y un dibujito de nube. ¿Qué nombre le damos?';
    }

    const tummyDiscomfort = /\b(?:tripa|tripota|barriga|barriguita|estomago)\b/.test(signals) && /\b(?:duele|dolor|molestia|molestias|revuelta|revuelto|mal)\b/.test(signals);
    if (characterId === 'salchicher' && painContext && /\b(?:desde|hace|ayer|dias|horas|no se me pasa)\b/.test(input)) {
      return 'Anoto cuánto lleva acompañándote, Patita. Vamos a la siguiente línea del cuaderno: ¿lo notas todo el rato o aparece y desaparece? El Oso puede acercarte compañía y una manta mientras charlamos.';
    }
    if (tummyDiscomfort && characterId === 'salchicher') {
      return 'Ay, esa tripota de pato, Patita. Puedes acomodarte, beber unos sorbitos de agua y pedir un abrazo de perro de los que no aprietan, si te apetece. En mi cuaderno dibujo unas gotas imaginarias de mojo de Oso. ¿Desde cuándo la notas así?';
    }
    if (tummyDiscomfort) {
      return 'Ay, esa tripota, Patita. Podemos ir despacito: un ratito tranquila y sorbitos de agua. Te acompaño con unas palabras suaves. ¿Ha empezado hace poquito?';
    }

    if (/\bmojo de oso\b/.test(input)) {
      return 'Saco el abrazómetro de cuento, Patita: vamos a revisar tus reservas de mojo de Oso. Para llenarlas, podemos pedir un abrazo o un ratito juntos cuidando las plumas, si te apetece. ¿El Oso te está dando mimos suficientes o anotamos que te vendrían bien más?';
    }
    if (characterId === 'salchicher' && /\b(?:autocuidado|cuidarme|habitos|cuidado cotidiano)\b/.test(input)) {
      return 'Me ajusto las gafitas, Patita. Para cuidarte en lo cotidiano podemos empezar por cosas sencillas: descansar, beber agua con normalidad, comer de forma variada y buscar un ratito tranquilo. Sin convertirlo en una lista de deberes. ¿Qué pequeño cuidado te apetece hoy?';
    }
    if (characterId === 'salchicher' && /^no tengo fiebre[.!\s]*$/.test(input)) {
      return 'Anotado en el cuaderno, Patita. Me acomodo las gafitas y seguimos despacito: ¿qué notas hoy en el pico, las alas o la tripota?';
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
