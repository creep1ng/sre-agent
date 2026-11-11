# Midnight — guion para la demo evaluada

**Duración objetivo:** unos 12 a 13 minutos, más preguntas. La demostración es en vivo: los tiempos son orientativos, no promesas. Para la feria del 10 de noviembre, usar el mismo recorrido y detenerse en la pregunta que traiga cada visitante.

**Voces:** Ricardo: apertura, problema, demo en vivo y cierre; Mario: solución; Camilo: resultados y costo (opera la consola y Telegram durante la demo, así que cuenta en segundos lo que acaba de pasar); Daniel: límites y lo que sigue. Ricardo narra la demo mientras Camilo navega.

**Preparación, antes de recibir al público**

- [ ] El equipo operador preparó la demo EC2 y comprobó la tienda, las conexiones y Telegram, siguiendo el [recorrido técnico](../demo-2026-11-04-script.md). Esta guía contiene los comandos y el restablecimiento entre ensayos.
- [ ] En T−3 minutos, antes de empezar las diapositivas, inyectar `paymentUnreachable`. La falla ya está activa cuando comienza la presentación; Grafana e investigación avanzan durante las diapositivas 1 a 3. El tiempo real puede variar.
- [ ] Abrir pestañas: diapositivas, `/app/acciones`, bandeja `/app/`, Telegram y Demo Dashboard de Grafana filtrado por `checkout`. Mostrar solo el dashboard o las reglas; no abrir los puntos de contacto de Grafana, que pueden mostrar un secreto.
- [ ] Comprobar que la proyección no exponga claves, direcciones, identificadores privados ni datos de clientes. Tener a mano los planes B del recorrido técnico.
- [ ] No aprobar una propuesta equivocada. Si la falla no se reproduce, decirlo y usar el plan B que corresponda; no narrar un resultado que no apareció.

## 1. Portada — 0:00–0:30

**En pantalla:** diapositiva 1, «midnight / Cierra el portátil. Midnight hace la guardia». **Voz:** Ricardo.

*Dejar un momento la portada en pantalla.*

**Decir:** «Buenas. Imaginen que mantienen las tiendas y aplicaciones de varios clientes. Terminan la jornada, cierran el portátil y se acuestan. Pero el teléfono sigue siendo de ustedes. Si algo falla, también les toca responder a ustedes.

Midnight nace de esa noche. Es nuestro proyecto aplicado: un prototipo que busca hacer la guardia con las señales que ya existen y pedirles una decisión cuando hace falta.»

## 2. El dolor — 0:30–1:25

**En pantalla:** diapositiva 2, «El dolor». **Voz:** Ricardo.

*Señalar el recorrido del problema, sin leer la diapositiva.*

**Decir:** «Una persona independiente o una agencia pequeña puede cuidar varios servicios sin tener un equipo de guardia. A veces el cliente descubre primero que no puede cobrar. Entonces vienen las llamadas, entrar al servidor de madrugada y buscar entre métricas y logs mientras el servicio sigue fallando.

También pasa lo contrario: llegan tantas alertas que uno termina ignorándolas. Y pagar herramientas para cada cliente puede pesar en un negocio pequeño. Al mismo tiempo, confiarle a un modelo acceso de administrador o las llaves de la nube no es una decisión ligera.

La pregunta que nos hicimos fue: ¿cómo ayudamos a esa persona a llegar a la mañana con una decisión clara y un registro de lo que pasó?»

## 3. La solución — 1:25–2:50

**En pantalla:** diapositiva 3, «La solución». **Voz:** Mario.

*Seguir con el dedo el flujo de izquierda a derecha.*

**Decir:** «Las operaciones con agentes son una categoría nueva y todavía incipiente. Con Midnight llegamos a este prototipo; hoy les vamos a mostrar cómo trabaja en un escenario concreto.

Una alerta de Grafana llega al motor. Midnight investiga: consulta métricas de Prometheus y logs en OpenSearch, y busca contexto en una base de conocimiento mediante RAG y en habilidades o *skills* preparadas para la tarea. La base aporta contexto; las mediciones son las que respaldan la hipótesis.

Después propone una operación del catálogo. Esta es la frase central: **definimos un catálogo de acciones que el agente no se puede inventar, ya probadas; el agente propone y el humano aprueba**. En esta demo, esa aprobación llega por Telegram o por la consola. Un ejecutor separado corre la operación permitida y deja un recibo. Luego Midnight vuelve a medir la señal y, si encuentra recuperación, prepara un borrador de postmortem para que una persona lo revise y cierre.

Buscamos silencio por defecto: interrumpir cuando una decisión humana cambia el resultado, no por cada señal. Pueden alojar Midnight ustedes mismos y aportar su modelo. También hay controles de identidad, permisos, asignación de modelos, consumo y auditoría, útiles si un cliente empresarial pide cumplimiento. Ahora veamos qué ocurre cuando se daña el pago.»

## 4. Demo en vivo — 2:50–8:45

**En pantalla:** consola RC-2 y después Grafana. **Voz:** Ricardo; Camilo opera. La falla fue inyectada antes de empezar. *Los minutos son una guía: adaptar el ritmo al estado real y narrar solo lo visible.*

| Paso y pantalla | Qué decir | Plan B si falla |
| --- | --- | --- |
| *Abrir `/app/acciones` y señalar `checkout · flag.set`.* | «Empezamos por los límites. Para este recorrido, la operación autorizada es cambiar una bandera de checkout a un valor permitido. No hay una terminal para que el agente invente comandos. En esta demo, nada de esto se ejecuta sin aprobación.» | Si la página no carga, decirlo; revisar el entorno con el operador y no fingir que se mostró el catálogo. |
| *Ir a la bandeja `/app/` y abrir el incidente.* | «Mientras hablábamos, una falla ya activa afectó los pagos. Grafana entrega la alerta y Midnight inicia la investigación sin que tengamos que abrir la consola. Aquí aparece lo que requiere atención.» | Si no aparece, «La alerta todavía no llegó; revisaremos el canal y las reglas». Seguir el [recorrido técnico](../demo-2026-11-04-script.md#the-walk); no atribuirle una resolución al agente. |
| *En el incidente, señalar el título y la hipótesis; recorrer la línea de tiempo.* | «El título trata de decirnos qué está fallando. La hipótesis es una interpretación, no una verdad garantizada. Podemos seguir sus fuentes: consultas PromQL, líneas de logs y contexto de la base de conocimiento, si aparecen en esta ejecución. El contexto ayuda a investigar; no reemplaza una medición.» | Si la investigación se detuvo sin propuesta, pulsar «Reintentar la investigación» y decir: «El primer intento no llegó a una propuesta; lo estamos reintentando». Si hay una hipótesis errada, señalarlo y no aprobarla. |
| *Mostrar la propuesta ámbar y el mensaje de Telegram.* | «El ámbar marca una decisión nuestra. Midnight propone poner `paymentUnreachable` en `off` para checkout. Revisamos tanto la evidencia como la operación antes de decidir. El catálogo delimita lo que puede pedir; no garantiza que su diagnóstico sea correcto.» | Si no llega Telegram, abrir la misma propuesta en la bandeja y aprobar desde allí. Si propone una bandera equivocada, rechazarla y dejar que vuelva a investigar; no presentarla como correcta. |
| *Pulsar «Aprobar» una sola vez en Telegram o en la consola. Mostrar el recibo y el estado «Verificando».* | «Nosotros aprobamos. El ejecutor separado aplica la operación permitida y queda el recibo: qué se ejecutó y quién lo autorizó. Ejecutar no equivale todavía a recuperar el servicio. Por eso el incidente queda verificando.» | Si no aparece recibo o falla la ejecución, decir qué sí se observó y detener el relato de éxito; consultar el recorrido técnico. |
| *Mantener visible «Verificando». Comenzar la conversación de espera de abajo.* | «Ahora esperamos la ventana de verificación. En esta configuración son aproximadamente dos minutos y medio desde la mitigación; la respuesta del modelo puede tardar más.» | Si no hay veredicto o solicita ayuda, revisar la señal y usar «El servicio está estable» solo si la persona comprobó que lo está. Decir explícitamente que fue una confirmación humana. Si sigue fallando, usar «Sigue fallando»; el sistema puede reinvestigar hasta dos veces y después pide intervención. |
| *Cuando aparezca, señalar «Servicio verificado estable» y «Resuelto». Mostrar la edición del mensaje en Telegram.* | «En esta ejecución, Midnight volvió a medir después del cambio y encontró estable el servicio. La consola dice “Resuelto” y el mismo mensaje de Telegram se actualiza. No necesitamos una nueva conversación para saber qué pasó.» | Si la recuperación se confirmó manualmente, decir: «Hoy la verificación automática no dio el veredicto; una persona confirmó la estabilidad». No describirla como automática. |
| *Abrir el postmortem; señalar «Borrador del agente».* | «Para la mañana queda una primera narración del incidente. El modelo redacta un borrador a partir del registro; la persona lo revisa. Las horas, la línea de tiempo y las acciones citadas provienen del registro.» | Si aparece «Borrador desde el registro», decir: «La llamada al modelo no produjo el borrador y mostramos el respaldo construido desde el registro». No llamarlo borrador del agente. |
| *Tras revisar, pulsar «Aprobar y cerrar» y mostrar «Cerrado».* | «Cerrar es una decisión humana. Así queda una historia que podemos revisar y compartir con el cliente.» | Si falla la vista actual, el recorrido técnico indica la consola anterior. Si tampoco funciona, decirlo y dejar el incidente sin presentar como cerrado. |
| *Abrir Grafana Demo Dashboard, `checkout`; señalar la curva después de la mitigación.* | «Esta es la señal externa que nos interesa: la tasa de errores de checkout bajando después del cambio. El recibo nos dice qué se hizo; la gráfica nos ayuda a ver qué pasó con el servicio.» | Si la gráfica no carga o aún no muestra la caída, decirlo. No inferir recuperación visual a partir del botón o del recibo. |

### Mientras corre la ventana de verificación

*Repartir esta conversación durante los aproximadamente 150 segundos. Dejar espacio para mirar el estado. Si termina antes, pasar a «Resuelto»; si tarda más, no inventar una conclusión.*

**Decir:** «En una guardia real, lo difícil no es solo recibir un aviso. Es decidir qué observar, entender qué cambió y hacer algo sin agrandar el problema. Por eso esta pantalla muestra la hipótesis junto con sus fuentes. Ustedes pueden discutirla y rechazarla.

El catálogo es el otro límite. La persona define de antemano qué operaciones están disponibles y sobre qué servicio. El modelo no recibe una sesión SSH para escribir cualquier comando. El ejecutor es otro componente: recibe una operación estructurada y aplica su contrato. Así podemos separar la propuesta de la ejecución y dejar un recibo para revisarlo después.

Eso no elimina todos los riesgos. Una acción permitida también puede ser equivocada para la situación. Por eso en este recorrido hay aprobación humana y después una nueva medición. Y si la señal sigue mal, no decimos que el incidente se arregló solo porque la operación terminó.

También pensamos en el bolsillo. En los ensayos, una investigación costó entre medio centavo y siete décimas de centavo de dólar en modelo, pero eso no es una factura mensual ni incluye toda la infraestructura. Nuestro objetivo es que el costo total por persona sea menor de un dólar al mes; todavía no lo hemos demostrado. Queremos medir casos más difíciles, con distintos modelos y con fallas incluidas.

Al final, lo valioso para la persona no es mirar esta consola toda la noche. Es poder recibir una decisión entendible en el canal que usa y encontrar al día siguiente la evidencia y el recibo. Estamos construyendo hacia esa experiencia; hoy estamos viendo un camino acotado.»

## 5. Resultados medidos — 8:45–10:15

**En pantalla:** diapositiva 4, «Una falla, de principio a fin», y luego la 5, «Por segundo de agente». **Voz:** Camilo.

*Las cifras son del ensayo en EC2 de hoy, 4 de noviembre, 17:09–17:21 UTC, con modelo real y métricas cada 10 s. Si la demo en vivo da otros números, decir los de hoy en vivo y dejar estos como el ensayo.*

**Decir (diapositiva 4):** «Esta es la falla que acaban de ver, contada en segundos. En el cero inyectamos la falla. A los 85 segundos los errores ya se ven en el dashboard, y a los 129 la regla de Grafana, que exige un minuto sostenido, abre el incidente sin nadie en la consola. Midnight investiga 37 segundos: seis llamadas al modelo, de la alerta a una propuesta con evidencia. Luego viene lo único que espera a una persona: un toque. Después de aprobar, la alerta de Grafana se resuelve a los 78 segundos; el primer pedido bueno aparece a los 18. Y a los 150 segundos Midnight mide por su cuenta y resuelve el incidente; el postmortem queda redactado 14 segundos después. Si la primera mitigación no funciona, vuelve a investigar solo. Es un ensayo, no un benchmark.»

**Decir (diapositiva 5):** «AWS ya vende esto, y lo cobra por segundo de agente: 0,0083 dólares. Esta investigación nos costó 0,0069 dólares en 37 segundos, unas 44 veces menos por segundo. Con el propio ejemplo de AWS, diez investigaciones de ocho minutos al mes cuestan 39,84 dólares; prorrateado, lo nuestro rondaría 90 centavos. Dos honestidades: lo de ocho minutos es prorrateo, no lo medimos; y AWS lee muchas más fuentes que nosotros. Nuestro costo es solo el modelo, sin el servidor.»

*Nota para el equipo:* el ensayo de hoy también abrió un segundo incidente en payment (cascada, #845), con otra investigación pagada. El costo de la diapositiva es solo el de checkout. Las cifras anteriores (31 de octubre, 2 y 3 de noviembre) siguen en [issue-765](../evidence/issue-765/ec2-paymentfailure.json), [ec2-catalog](../evidence/ec2-catalog-2026-11-02/README.md) y [la octava ronda](../product-direction-2026-10-28.md#eighth-round-of-decisions-2026-11-03-afternoon), por si preguntan.

## 6. Limitaciones de la demo actual — 10:15–11:00

**En pantalla:** diapositiva 6, «Lo que esta demo todavía no demuestra». **Voz:** Daniel.

**Decir:** «Esto es un prototipo académico, y queremos ser claros con lo que todavía no demuestra.

Falta probarlo con sistemas reales o en producción: hoy es un entorno, la tienda de OpenTelemetry Demo, y una familia de fallas, los flags de pago. No hemos medido su factual rate: falta la evaluación ciega con rúbrica fija frente a Claude Code, y las pruebas de inyección. Y falta un catálogo de acciones más amplio, ejecutable sobre infraestructura real; hoy el recorrido apaga un flag, y rollback y reinicio existen en el ejecutor, pero no en esta demo.

Si rechazan una propuesta, la investigación termina; todavía no se puede pedir cambios ni conversar con el agente. Una falla en cascada abre dos incidentes, porque aún no correlacionamos alertas; lo vieron hoy, con payment. Faltan fuentes para investigar: hoy lee Grafana, Prometheus y OpenSearch, todavía no Slack, Notion, GitHub ni CI/CD. Y el costo se midió en investigaciones cortas; una falla con código y CI/CD hará crecer el contexto, y "menos de un dólar al mes" es una meta. Si algo falla hoy en vivo, lo diremos y mostraremos qué parte sí funcionó.»

## 7. Lo que sigue — 11:00–12:00

**En pantalla:** diapositiva 7, «Hoy apaga un flag. Mañana cuida tu deploy del viernes». **Voz:** Daniel.

*Señalar la línea: nadie de guardia a la izquierda, un agente con SSH root a la derecha, Midnight en el medio, las suites empresariales arriba.*

**Decir:** «Las grandes ya llegaron aquí. AWS tiene DevOps Agent, y Rootly, PagerDuty o Datadog tienen sus agentes: eso nos dice que operar con agentes es hacia donde va la industria. Pero están hechos para equipos con licencia. Para quien mantiene solo los servicios de sus clientes, hoy hay dos extremos: no tener a nadie de guardia, o darle root a un modelo por SSH. En el medio no hay nada pensado para una persona. Ese hueco es Midnight.

Hoy apaga un flag. Lo siguiente es cuidar el deploy del viernes: vigilar la ventana después de cada deploy de GitHub Actions y proponer el rollback si algo se cae. Que recuerde los incidentes de cada cliente y cite de dónde sale cada recuerdo. Que lo reversible y ya probado corra solo, y lo demás te pregunte. Que puedan decidir desde Telegram, desde la API o desde Claude Code por MCP, porque el motor es el producto y las interfaces son clientes. Y publicar cada noche una evaluación, con las corridas fallidas incluidas.

Más lejos, nos entusiasma esto: catálogos para Railway, Fargate o el VPS de cada quien, con el modelo que cada uno quiera, también uno local. Y cuando Midnight ya conozca la arquitectura de tus servicios, que encuentre la exposición antes que un atacante y te proponga el parche.

Para el negocio pensamos en dos caminos: código abierto que cada quien aloja, y más adelante una nube administrada con un conector pequeño en tu servidor. Es una hipótesis por validar, igual que el precio. Si logramos que una persona cuide varios servicios y duerma, esa noche cambia, y también la conversación con el cliente a la mañana siguiente.»

## 8. Cierre y preguntas — 12:00–12:30

**En pantalla:** diapositiva 8, «Cierre + preguntas». **Voz:** Ricardo.

*Volver a la portada visual o dejar el cierre en pantalla.*

**Decir:** «Midnight busca que puedan cerrar el portátil sabiendo que hay una guardia que observa, explica y les pide permiso para actuar. Hoy les mostramos un primer recorrido, con sus límites y sus mediciones. Queremos escuchar sus preguntas y qué necesitarían ustedes para confiar en una herramienta así.»

## Q&A preparado

**1. ¿Cómo se detecta la falla y quién consulta?**  
En esta demo, Prometheus recoge métricas de los servicios instrumentados y Grafana evalúa reglas sobre esas series; cuando una alerta se activa, la envía por webhook a Midnight. La consola no tiene que estar abierta para iniciar la investigación. La regla preparada para la demo se evalúa cada 10 segundos en Grafana y exige un minuto en condición de alerta; el colector vuelca las métricas de spans cada 10 segundos en la instancia de la demo. Prometheus no sondea esas métricas: el colector se las empuja por OTLP, así que el ritmo lo fija ese volcado (60 s en upstream; 10 s en nuestra instancia EC2 desde hoy, para ver la recuperación en Grafana en cerca de un minuto, esperado y aún no medido). [Regla](../../demo/grafana/alerting/midnight.yaml); [configuración del colector](../../scripts/otel_demo/mcp_guest.py).

**2. ¿Cuánto demora y qué pasa si consultamos más rápido?**  
En la prueba EC2 del 31 de octubre con `paymentFailure`, la activación hasta el despacho fue 103,5 s para payment y 164,9 s para checkout; con `paymentUnreachable` puede variar. Depende de recolección, evaluación, ventana y persistencia de la regla, transporte e investigación. Consultar más rápido puede reducir una parte de la espera, pero aumenta carga y costo y puede amplificar ruido; no hemos medido ese intercambio aquí.

**3. ¿Qué tan a menudo alucina o se equivoca?**  
No tenemos una tasa medida ni afirmamos una precisión. Planeamos una evaluación ciega con una rúbrica fijada antes de las corridas, una línea base de Claude Code con las mismas señales y reporte de todos los intentos, incluidos los fallidos; también pruebas de inyección de instrucciones y alucinaciones guiadas por MITRE ATLAS y NIST AI RMF.

**4. ¿Por qué no un árbol de decisión o una máquina de estados?**  
El ciclo sí tiene fases y límites fijos: investigar, pedir aprobación, ejecutar y verificar. El modelo ayuda a explorar señales y elegir una propuesta dentro del catálogo; los protocolos de cada cliente se pueden aportar como conocimiento y habilidades, sin escribir un árbol para cada combinación de síntomas. La comparación rigurosa con una alternativa determinista queda por evaluar.

**5. ¿Qué impide que el agente haga cualquier cosa?**  
La operación debe existir en el catálogo y cumplir su contrato; en este recorrido requiere además aprobación humana antes de que un ejecutor separado la realice. No le entregamos una terminal SSH general al modelo para que improvise comandos. Una acción permitida todavía puede ser inadecuada, de ahí la revisión y la verificación.

**6. ¿Qué pasa si se equivoca de bandera o el servicio sigue fallando?**  
No aprobamos una propuesta equivocada; se puede rechazar y el agente vuelve a buscar evidencia. Si una mitigación aprobada falla la verificación, el sistema vuelve a investigar con el intento fallido en contexto, hasta dos reinvestigaciones por incidente; después pide ayuda humana.

**7. ¿Cómo sabemos que la acción funcionó?**  
El recibo prueba lo que ejecutó el componente, no que el servicio sanó. Midnight vuelve a consultar la señal después de la mitigación; si no produce un veredicto, una persona puede comprobar el servicio y confirmar manualmente. Una gráfica en Grafana ayuda a revisar la evolución, sin convertir un solo caso en garantía.

**8. ¿Para qué sirve la base de conocimiento?**  
Guarda contexto y procedimientos para orientar la investigación, recuperados mediante RAG; las habilidades aportan instrucciones de trabajo. Una entrada de conocimiento no es por sí sola evidencia medida de que una causa ocurrió. La persona debe poder revisar la procedencia y aprobar cambios propuestos a esa memoria.

**9. ¿Por qué esta interfaz?**  
Está pensada para entrar cuando hay algo que decidir: el ámbar señala la decisión, y la hipótesis se conecta con una línea de tiempo y sus fuentes. La consola permite revisar con calma por la mañana; Telegram busca llevar la decisión a donde ya está la persona. Es una dirección de diseño que aún necesita validación con usuarios.

**10. ¿Puedo hablar directamente con el modelo?**  
Hoy el usuario no conversa directamente con el modelo dentro del producto. Esa superficie más pequeña reduce una vía de inyección, pero los logs y documentos también son entradas no confiables; debemos probar esas amenazas y no declararlas resueltas.

**11. ¿Cómo se compara con AWS DevOps Agent, Google/Wiz, Rootly, PagerDuty o Datadog?**  
Son referencias importantes con distintas capacidades y recursos; no hemos completado una comparación funcional y de costos que permita declarar superioridad. Nuestra apuesta es una persona con varios servicios, software autoalojable, el modelo que elijas (hoy por OpenRouter; la inferencia local es exploración), operaciones catalogadas y una meta de costo pequeño. Debemos validar tanto esa diferenciación como la compatibilidad de cada modelo y entorno.

**12. ¿Cuánto cuesta?**  
En EC2, el 2 de noviembre, tres investigaciones costaron USD 0,0137 en modelo, cerca de medio centavo cada una; hoy, 4 de noviembre, la de checkout costó USD 0,0069 en 37 s (el ensayo del 19 de octubre registró USD 0,002–0,005); no incluye necesariamente todos los costos de operar el producto. Menos de USD 1 por usuario al mes es una meta, no una medición ni un precio anunciado. Casos complejos, infraestructura, monitoreo y proveedores pueden cambiar la cuenta.

**13. ¿Cómo ganarían dinero?**  
Exploramos una versión abierta autoalojada y, más adelante, un servicio administrado de pago con un conector pequeño en el entorno del usuario. Ni la oferta ni el precio están decididos; primero hay que validar necesidades, costos y disposición a pagar.

**14. ¿Dónde encaja la gobernanza?**  
Para la persona independiente lo principal es saber qué pasó y decidir; no debería tener que aprender una estructura empresarial para empezar. Cuando un cliente exija cumplimiento, existen capacidades de identidades, claves con alcance, permisos, asignación de modelos, límites de consumo y auditoría que ayudan a responder quién puede hacer qué y qué ocurrió.

**15. ¿Qué pasa si falla Telegram, el modelo o la verificación?**  
Si Telegram no llega, se puede aprobar desde la bandeja. Si la investigación se detiene, se puede reintentar; si el modelo no redacta el postmortem, aparece un borrador identificado como proveniente del registro. Si la verificación no concluye, una persona puede comprobar y confirmar la estabilidad; no presentaremos esa confirmación como automática.

**16. ¿Qué falta antes de confiarle servicios reales?**  
Hace falta evaluar a ciegas más escenarios, seguridad y fallas, comprobar recuperación ante caídas y medir el costo completo y las interrupciones en uso sostenido. También hacen falta instalaciones y comentarios externos; el [backlog](../backlog-2026-12-04.md) recoge esas líneas como trabajo futuro, no como resultados ya logrados.

## Frases clave

- «Cierra el portátil. Midnight hace la guardia.»
- «El agente propone; el humano aprueba.»
- «Lo que no está en el catálogo no se ejecuta.»
- «Un recibo dice qué hicimos; una nueva medición dice qué pasó después.»
- «Silencio por defecto: interrumpir cuando una decisión humana cambia el resultado.»
- «El motor es el producto; las interfaces son clientes.»
- «Afirmamos lo que medimos; lo demás es una meta o está por medir.»
