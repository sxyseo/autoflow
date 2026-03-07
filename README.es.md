# Autoflow

<div align="center">

**Plano de Control de Entrega de Software Autónoma**

Inspirado en la filosofía "Harness Engineering" de OpenAI y flujos de trabajo de desarrollo impulsados por IA

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md)**

</div>

---

## Tabla de Contenidos

- [Resumen](#resumen)
- [Filosofía](#filosofía)
- [Conceptos Clave](#conceptos-clave)
- [Arquitectura](#arquitectura)
- [Características](#características)
- [Inicio Rápido](#inicio-rápido)
- [Configuración](#configuración)
- [Uso](#uso)
- [Temas Avanzados](#temas-avanzados)
- [Mejores Prácticas](#mejores-prácticas)
- [Solución de Problemas](#solución-de-problemas)
- [Contribuir](#contribuir)
- [Licencia](#licencia)

## Resumen

**Autoflow** es un plano de control ligero para la entrega de software autónoma. Permite que los agentes de IA ejecuten bucles repetibles alrededor de la creación de especificaciones, descomposición de tareas, implementación, revisión y mantenimiento, mientras delegan el trabajo de codificación concreto a varios backends de agentes de IA.

### Lo que Hace Único a Autoflow

A diferencia de las herramientas de desarrollo tradicionales, Autoflow está construido desde cero para el **desarrollo impulsado por IA**:

- **Estado como Fuente de Verdad**: Cada especificación, tarea, ejecución y decisión se rastrea explícitamente
- **Prompts Deterministas**: Habilidades y plantillas reutilizables garantizan un comportamiento consistente del agente
- **Backends Intercambiables**: Use múltiples agentes de IA de manera intercambiable
- **Ejecución en Segundo Plano**: Los agentes se ejecutan autónomamente a través de `tmux` sin bloquear flujos de trabajo
- **Puertas Automatizadas**: Revisiones, pruebas y controles de fusión previenen commits incorrectos
- **Recuperación Completa**: Cada ejecución se registra y es reanudable para transparencia y depuración

### El Objetivo: IA Autónoma Confiable

La meta inicial **no** es la autonomía total—es un **harness confiable** donde:

- Los humanos definen objetivos, límites y criterios de aceptación
- La IA opera autónomamente dentro de esas restricciones
- Cada cambio se prueba, revisa y confirma atómicamente
- Las iteraciones fallidas activan automáticamente correcciones, no intervención humana

## Filosofía

### Harness Engineering

Autoflow está inspirado en la filosofía [Harness Engineering de OpenAI](https://openai.com/index/harness-engineering/): **los agentes fuertes provienen de harnesses fuertes**.

Un harness proporciona:
- **Evaluación**: Métricas claras para éxito y fracaso
- **Orquestación**: Flujos de trabajo multi-agente coordinados
- **Puntos de Control**: Capacidad de recuperación y reversión
- **Contratos**: Interfaces bien definidas para el uso de herramientas

### Bucles de Auto-Completado de IA

Autoflow permite ciclos de desarrollo autónomo:

```
Codificación IA Tradicional:
Humano descubre problema → Humano escribe prompt → IA escribe código → Humano verifica → (repetir)

Flujo de Trabajo Autoflow:
IA descubre problema → IA corrige → IA prueba → IA confirma → (bucle cada 1-2 minutos)
```

**Perspectivas clave**:
1. **Las pruebas automatizadas son requisito previo**: Cada commit debe pasar las pruebas
2. **Bucles de auto-completado de IA**: La IA descubre, corrige, prueba y confirma autónomamente
3. **Commits de grano fino**: Cambios pequeños (pocas líneas) permiten iteración rápida y segura
4. **Humano en el bucle para reglas, no ejecución**: Humanos establecen límites; IA maneja ejecución

### Desarrollo Impulsado por Especificaciones

Autoflow aplica principios de desarrollo impulsado por especificaciones:

- **Especificación** define intención, restricciones y criterios de aceptación
- **Tareas** definen unidades de trabajo con dependencias y estado
- **Habilidades** definen flujos de trabajo reutilizables para cada rol
- **Ejecuciones** almacenan ejecuciones concretas con contexto completo
- **Agentes** mapean roles lógicos a backends de IA concretos

## Conceptos Clave

### Jerarquía de Estado

```
.autoflow/
├── specs/           # Intención y restricciones del producto
│   └── <slug>/
│       ├── SPEC.md              # Requisitos y restricciones
│       ├── TASKS.json           # Grafo de tareas y estado
│       ├── QA_FIX_REQUEST.md    # Hallazgos de revisión (markdown)
│       ├── QA_FIX_REQUEST.json  # Hallazgos de revisión (estructurado)
│       └── events.jsonl         # Registro de eventos
├── tasks/           # Definiciones y estado de tareas
├── runs/            # Prompts, logs, salidas por ejecución
│   └── <timestamp>-<role>-<spec>-<task>/
│       ├── prompt.md            # Prompt completo enviado al agente
│       ├── summary.md           # Resumen del agente
│       ├── run.sh               # Script de ejecución
│       └── metadata.json        # Metadatos de ejecución
├── memory/          # Captura de memoria con ámbito
│   ├── global.md                # Lecciones entre especificaciones
│   └── specs/
│       └── <slug>.md            # Contexto por especificación
├── worktrees/       # Árboles de trabajo git por especificación
└── logs/            # Registros de ejecución
```

### Flujo de Trabajo de Estado de Tareas

```
todo → in_progress → in_review → done
                   ↓           ↑
              needs_changes    |
                   ↓           |
                blocked ←─────┘
                   ↓
                  todo
```

**Estados válidos**:
- `todo`: Listo para comenzar
- `in_progress`: Actualmente siendo ejecutado
- `in_review`: Esperando revisión
- `done`: Completado y aprobado
- `needs_changes`: La revisión encontró problemas
- `blocked`: Esperando dependencias

### Resultados de Ejecución

**Resultados válidos**:
- `success`: Tarea completada exitosamente
- `needs_changes`: Completado pero requiere correcciones
- `blocked`: No puede proceder debido a dependencias
- `failed`: Ejecución fallida

### Habilidades y Roles

Autoflow define **habilidades** como flujos de trabajo reutilizables:

| Habilidad | Rol | Descripción |
|-----------|-----|-------------|
| `spec-writer` | Planificador | Convierte intención en especificaciones estructuradas |
| `task-graph-manager` | Arquitecto | Deriva y refina el grafo de ejecución |
| `implementation-runner` | Implementador | Ejecuta segmentos de codificación con ámbito limitado |
| `reviewer` | Aseguramiento de Calidad | Ejecuta revisión, regresión y controles de fusión |
| `maintainer` | Operador | Triaje de problemas, actualizaciones de dependencias, limpieza |

Cada habilidad incluye:
- **Descripción del flujo de trabajo**: Proceso paso a paso
- **Marco de rol**: Plantillas para comportamiento consistente del agente
- **Reglas y restricciones**: Qué puede y no puede hacer el agente
- **Formato de salida**: Artefactos esperados y entregas

### Protocolos de Agente

Autoflow soporta múltiples protocolos de agente:

#### Protocolo CLI (codex, claude)

```json
{
  "protocol": "cli",
  "command": "claude",
  "args": ["--full-auto"],
  "model_profile": "implementation",
  "memory_scopes": ["global", "spec"],
  "resume": {
    "mode": "subcommand",
    "subcommand": "resume",
    "args": ["--last"]
  }
}
```

#### Protocolo ACP (acp-agent)

```json
{
  "protocol": "acp",
  "transport": {
    "type": "stdio",
    "command": "my-agent",
    "args": []
  },
  "prompt_mode": "argv"
}
```

## Arquitectura

### Sistema de Cuatro Capas

```
┌─────────────────────────────────────────────────────────────┐
│                  Capa 4: Gobernanza                         │
│              Puertas de Revisión, CI/CD, Política de Ramas   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                  Capa 3: Ejecución                          │
│           Especificación, Rol, Agente, Prompt, Espacio      │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                  Capa 2: Roles (Habilidades)                │
│    Spec-Writer, Task-Graph-Manager, Implementation-Runner,  │
│              Reviewer, Maintainer, Iteration-Manager         │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                  Capa 1: Plano de Control                   │
│              Estado, Config, Memoria, Descubrimiento         │
└─────────────────────────────────────────────────────────────┘
```

## Características

### 1. Gestión de Estado Explícita

Cada aspecto del proceso de desarrollo se rastrea explícitamente:

- **Especificaciones**: Intención, requisitos, restricciones, criterios de aceptación
- **Tareas**: Unidades de trabajo con dependencias, estado y asignaciones
- **Ejecuciones**: Historial completo de ejecución con prompts, salidas y metadatos
- **Memoria**: Captura de aprendizaje con ámbito entre especificaciones y ejecuciones
- **Eventos**: Registros de eventos por especificación para auditoría y recuperación

### 2. Ensamblaje de Prompts Determinista

Autoflow garantiza un comportamiento consistente del agente a través de:

- **Definiciones de habilidades**: Flujos de trabajo reutilizables con pasos claros
- **Plantillas de rol**: Marco de rol para personalidades consistentes de agentes
- **Inyección de contexto**: Inclusión automática de estado relevante, memoria y hallazgos
- **Versionamiento de prompts**: Prompt completo almacenado con cada ejecución para reproducibilidad

### 3. Backends de Agente Intercambiables

Soporte para múltiples backends de IA a través de protocolos unificados:

- **Protocolo CLI**: Para agentes de línea de comandos (claude, codex)
- **Protocolo ACP**: Para agentes del Protocolo de Comunicación de Agentes
- **Continuación nativa**: Mecanismos de reanudación específicos del agente
- **Respaldo dinámico**: Selección automática de agente en fallas

### 4. Ejecución en Segundo Plano

Operación autónoma a través de `tmux`:

- **Sin bloqueo**: Las ejecuciones se ejecutan en segundo plano sin interrumpir flujos de trabajo
- **Adaptable**: Monitorea ejecuciones en tiempo real o revisa logs más tarde
- **Reanudable**: Soporte de continuación nativa para ejecuciones interrumpidas
- **Gestión de recursos**: Límites de ejecución concurrentes por agente y especificación

### 5. Puertas de Revisión y Fusión

Controles de calidad automatizados previenen commits incorrectos:

- **Hallazgos estructurados**: Artefactos QA legibles por máquina con ubicación, severidad y correcciones
- **Aprobación basada en hash**: El hash de implementación debe coincidir con la revisión aprobada
- **Aplicación de puerta**: El sistema bloquea la implementación después de cambios de planificación
- **Reintentos impulsados por tareas**: Hallazgos estructurados inyectados en prompts de corrección

### 6. Memoria y Aprendizaje

Sabiduría acumulada entre ejecuciones:

- **Memoria global**: Lecciones y patrones entre especificaciones
- **Memoria de especificación**: Contexto e historial por especificación
- **Memoria de estrategia**: Playbooks para bloqueadores repetidos
- **Captura automática**: Memoria extraída de ejecuciones exitosas
- **Inyección de prompt**: Contexto incluido automáticamente basado en configuración de agente

### 7. Aislamiento de Árbol de Trabajo

Desarrollo paralelo seguro:

- **Árboles de trabajo por especificación**: Árboles de trabajo git aislados
- **Repositorio principal limpio**: La rama principal permanece impecable
- **Fusión atómica**: Cambios fusionados solo después de aprobación
- **Reversión fácil**: Revertir árbol de trabajo en falla

### 8. Iteración Continua

Desarrollo autónomo programado:

- **Bucle basado en ticks**: Verificar, confirmar, despachar, empujar
- **Auto-commit**: Commits descriptivos con mensajes prefijados
- **Verificación**: Pruebas y controles pre-commit
- **Seguimiento de progreso**: Avance automático del estado de tareas

## Inicio Rápido

### Requisitos Previos

- Python 3.10 o superior
- Git
- tmux
- Un backend de agente de IA (Claude Code, Codex, o personalizado)

### Instalación

```bash
# Clonar el repositorio
git clone https://github.com/your-org/autoflow.git
cd autoflow

# (Opcional) Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### Inicialización

```bash
# 1. Configurar directorios de estado local
python3 scripts/autoflow.py init

# 2. Inicializar configuración del sistema
python3 scripts/autoflow.py init-system-config

# 3. Copiar y personalizar configuración de agentes
cp config/agents.example.json .autoflow/agents.json

# 4. Editar configuración de agentes para agregar sus backends de IA
# Edite .autoflow/agents.json para configurar sus agentes

# 5. Descubrir y sincronizar agentes locales/ACP
python3 scripts/autoflow.py sync-agents
```

### Cree Su Primera Especificación

```bash
python3 scripts/autoflow.py new-spec \
  --slug my-first-project \
  --title "Mi Primer Proyecto IA" \
  --summary "Construir una aplicación increíble impulsada por IA"
```

### Genere Grafo de Tareas

```bash
# Deje que la IA descomponga su especificación en tareas
python3 scripts/autoflow.py init-tasks --spec my-first-project

# Ver el estado del flujo de trabajo
python3 scripts/autoflow.py workflow-state --spec my-first-project
```

### Inicie Desarrollo Autónomo

```bash
# Habilite iteración continua
python3 scripts/continuous_iteration.py \
  --spec my-first-project \
  --config config/continuous-iteration.example.json \
  --commit-if-dirty \
  --dispatch \
  --push
```

¡Eso es todo! Autoflow ahora:
1. Verificará trabajo completado
2. Confirmará cambios con mensajes descriptivos
3. Ejecutará pruebas de verificación
4. Despachará la siguiente tarea lista
5. Iniciará agente en segundo plano
6. Repetirá cada 2-5 minutos

## Configuración

### Configuración de Agente (`.autoflow/agents.json`)

```json
{
  "agents": {
    "claude-impl": {
      "name": "Agente de Implementación Claude",
      "protocol": "cli",
      "command": "claude",
      "args": ["--full-auto"],
      "model_profile": "implementation",
      "tool_profile": "default",
      "memory_scopes": ["global", "spec"],
      "roles": ["implementation-runner", "maintainer"],
      "max_concurrent": 3,
      "resume": {
        "mode": "subcommand",
        "subcommand": "resume",
        "args": ["--last"]
      }
    },
    "codex-spec": {
      "name": "Agente de Especificación Codex",
      "protocol": "cli",
      "command": "codex",
      "args": ["--full-auto"],
      "model_profile": "spec",
      "tool_profile": "spec-tools",
      "memory_scopes": ["global"],
      "roles": ["spec-writer", "task-graph-manager"],
      "max_concurrent": 2
    }
  }
}
```

### Configuración del Sistema (`.autoflow/system.json`)

```json
{
  "memory": {
    "enabled": true,
    "scopes": ["global", "spec", "strategy"],
    "auto_capture": true,
    "global_memory_path": ".autoflow/memory/global.md",
    "spec_memory_dir": ".autoflow/memory/specs",
    "strategy_memory_dir": ".autoflow/memory/strategy"
  },
  "model_profiles": {
    "spec": {
      "model": "claude-sonnet-4-6",
      "temperature": 0.7,
      "max_tokens": 8192
    },
    "implementation": {
      "model": "claude-sonnet-4-6",
      "temperature": 0.3,
      "max_tokens": 16384
    },
    "review": {
      "model": "claude-opus-4-6",
      "temperature": 0.2,
      "max_tokens": 16384
    }
  },
  "tool_profiles": {
    "default": {
      "allowed_tools": ["read", "write", "edit", "bash", "search"],
      "denied_tools": []
    },
    "spec-tools": {
      "allowed_tools": ["read", "write", "edit", "search"],
      "denied_tools": ["bash"]
    }
  },
  "acp_registry": {
    "enabled": true,
    "discovery_paths": [
      "/usr/local/bin/acp-agents/*",
      "~/.local/share/acp-agents/*"
    ]
  }
}
```

## Uso

### Comandos Básicos

#### Gestión de Especificaciones

```bash
# Crear nueva especificación
python3 scripts/autoflow.py new-spec \
  --slug <spec-slug> \
  --title "<title>" \
  --summary "<summary>"

# Actualizar especificación existente
python3 scripts/autoflow.py update-spec --slug <spec-slug>

# Ver detalles de especificación
python3 scripts/autoflow.py show-spec --slug <spec-slug>
```

#### Gestión de Tareas

```bash
# Inicializar tareas para una especificación
python3 scripts/autoflow.py init-tasks --spec <spec-slug>

# Mostrar estado del flujo de trabajo
python3 scripts/autoflow.py workflow-state --spec <spec-slug>

# Actualizar estado de tarea
python3 scripts/autoflow.py update-task \
  --spec <spec-slug> \
  --task <task-id> \
  --status <status>

# Mostrar historial de tareas
python3 scripts/autoflow.py task-history \
  --spec <spec-slug> \
  --task <task-id>
```

#### Gestión de Ejecuciones

```bash
# Crear nueva ejecución
python3 scripts/autoflow.py new-run \
  --spec <spec-slug> \
  --role <role> \
  --agent <agent-name> \
  --task <task-id>

# Iniciar ejecución en tmux
scripts/tmux-start.sh .autoflow/runs/<run-id>/run.sh

# Adjuntar a sesión en ejecución
tmux attach -t autoflow-run-<timestamp>

# Completar una ejecución
python3 scripts/autoflow.py complete-run \
  --run <run-id> \
  --result <success|needs_changes|blocked|failed> \
  --summary "<summary>"
```

## Mejores Prácticas

### 1. Comience con Fundamentos Sólidos

- Invierta en cobertura de pruebas completa desde el principio
- Defina criterios de aceptación claros para cada tarea
- Configure puertas CI/CD antes de la operación autónoma

### 2. Defina Límites Claros

- Especifique qué puede y no puede hacer la IA autónomamente
- Establezca límites de recursos (tiempo, memoria, llamadas API)
- Defina disparadores de escalación para intervención humana

### 3. Confíe Pero Verifique

- Deje que la IA opere autónomamente dentro de los límites
- Monitoree salidas periódicamente, no constantemente
- Intervenga solo cuando se violen los límites

### 4. Abraze la Iteración Rápida

- Cambios pequeños y enfocados > PRs grandes
- Bucles de retroalimentación rápidos > planificación perfecta
- Recuperación automatizada > depuración manual

### 5. Aprenda y Adapte

- Revise decisiones de IA semanalmente
- Actualice límites basándose en patrones
- Consolide lecciones aprendidas en memoria

## Solución de Problemas

### Las Ejecuciones del Agente se Bloquean o Cuelgan

```bash
# Verificar sesiones tmux activas
tmux ls

# Adjuntar a sesión específica para depurar
tmux attach -t autoflow-run-<timestamp>

# Matar sesión atascada
tmux kill-session -t autoflow-run-<timestamp>
```

### Las Tareas Fallan Continuamente

```bash
# Examinar historial de tareas para patrones
python3 scripts/autoflow.py task-history --spec <spec> --task <task-id>

# Verificar si existe solicitud de corrección
python3 scripts/autoflow.py show-fix-request --spec <spec>

# Ver ejecuciones recientes para la tarea
ls -lt .autoflow/runs/ | grep <task-id>

# Avanzar tarea bloqueada manualmente
python3 scripts/autoflow.py update-task \
  --spec <spec> \
  --task <task-id> \
  --status todo
```

## Contribuir

¡Bienvenimos las contribuciones! Por favor vea [CONTRIBUTING.md](CONTRIBUTING.md) para guías.

## Licencia

Licencia MIT - ver archivo [LICENSE](LICENSE) para detalles

---

<div align="center">

**[⬆ Volver Arriba](#autoflow)**

Hecho con ❤️ por la comunidad de Autoflow

</div>
