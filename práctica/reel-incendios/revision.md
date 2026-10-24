# Revisión del guion: Qwen frente a DeepSeek

Texto fuente: el README del Reto C (`../reto-c-incendios/README.md`). Las dos respuestas vienen del mismo prompt (`prompt.txt`), pegado en chat.deepseek.com y en chat.qwen.ai el 24 de octubre de 2026.

**Control automático (`guion.py`).** Las dos pasaron: todas sus cifras aparecen tal cual en el texto. Los errores que siguen los encontré leyendo cada frase contra el README.

## ¿Cuál inventó menos?

**DeepSeek inventó menos.** Respetó que el 56 % es «de la huella» y, en LinkedIn, copió las cuatro limitaciones. Sus fallas son de forma: frases torpes y un error de concordancia.

**Qwen escribió mejor y exageró más.** Sus frases suenan a reel, pero en tres lugares dijo más de lo que dice el texto.

| Escena | Qwen | DeepSeek | Qué dice el README |
|---|---|---|---|
| Pastizal | «el 56 % de **lo que se quemó en Perú** fue pastizal» | «en la huella… el 56 % era pastizal» | 56 % de la *huella* (zona con fuego) de los 730 incendios de 100 ha o más. La huella no es el área quemada, y no es todo el Perú. |
| Donaciones | «**la sociedad civil** recaudó S/ 501 570 **para equipar** a ocho comandancias» | «Perú Pendiente recaudó… para la respuesta» | Recaudó una ONG, Perú Pendiente, y el **88 %** fue en equipos; el resto fue ayuda humanitaria y saldo. |
| Río Tambo | «se quemaron 3 266 ha» | «medí 3 266 ha… fue la excepción de bosque amazónico» | Es la medición satelital; las nubes taparon 1 729 ha y triplica la cifra oficial, que seguía en evaluación. Ninguno conservó esa advertencia. |
| Bomberos | «45 km en línea recta» ✔ | «45 km» (sin «en línea recta») | Distancia mediana en línea recta. |
| Edificaciones | «7 722 edificaciones» ✔ | «**siete mil setecientos** veintidós» (concordancia) y sin «a menos de 1 km» | 7 722 edificaciones a menos de 1 km de los 20 incendios más grandes. |
| Posts | Repiten «el 56 % de lo quemado en Perú» y «la sociedad civil… para equipar» | Fieles, con las limitaciones en LinkedIn | — |

## Qué corregí y por qué

1. **«De lo que se quemó en Perú» → «de la zona con fuego de los incendios grandes».** El 56 % se midió sobre la huella de los incendios de 100 ha o más, cruzada con WorldCover 2021. Decir «lo que se quemó en el Perú» generaliza a todo el país y confunde huella con área quemada.
2. **«La sociedad civil… para equipar» → «La ONG Perú Pendiente recaudó… y el 88 % fue en equipos».** Es una sola organización, y no todo el dinero fue a equipos.
3. **Río Tambo: agregué «el satélite mide» y «las nubes taparon otra parte».** Es una estimación satelital, no la cifra oficial, y hay 1 729 ha que ningún satélite vio. La regla 1 del prompt pedía conservar las advertencias y ninguno de los dos modelos lo hizo.
4. **Bomberos: dejé «en línea recta»** (de Qwen). El trayecto real es más largo.
5. **Edificaciones: «siete mil setecientas veintidós… a menos de un kilómetro».** Concordancia con «edificaciones» y la distancia que da sentido a la cifra.
6. **Cierre: fuentes en palabras que la voz pronuncia bien** («Sentinel dos») y el periodo en pantalla.
7. **Posts:** partí de los de DeepSeek, quité las generalizaciones de Qwen y agregué «Voz generada con IA.» en los tres. Todos quedan dentro del largo pedido (495, 201 y 811 caracteres).

Lección: los números se verifican con código; las afirmaciones, leyendo. Las dos respuestas tenían todas las cifras bien y aun así una de ellas decía algo falso.
