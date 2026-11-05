export const meta = {
  name: 'proofread-case',
  description: 'Сплошная вычитка одного дела: редактор и независимый ревьюер на каждую порцию сцен',
  phases: [
    { title: 'Редактура', detail: 'редактор по editor.md на порцию сцен' },
    { title: 'Ревью', detail: 'независимый ревьюер по reviewer.md' },
  ],
}

const CASE = args.case
const DIR = `work/proofread-2026-11/c${CASE}/`
const ITEMS = args.chunks.map((chunk, i) => ({ chunk, prev: args.prev[i], done: args.done[i] }))

const SUMMARY = {
  type: 'object',
  properties: {
    scenes: { type: 'array', items: { type: 'string' } },
    lines: { type: 'integer' },
    edits: { type: 'integer' },
    questions: { type: 'integer' },
    highlights: { type: 'array', items: { type: 'string' }, description: '2-3 показательные правки: было → стало — почему' },
    problems: { type: 'string', description: 'что мешало или было неясно; пусто, если ничего' },
  },
  required: ['scenes', 'lines', 'edits', 'questions', 'highlights', 'problems'],
}

const REVIEW = {
  type: 'object',
  properties: {
    scenes: { type: 'array', items: { type: 'string' } },
    accept: { type: 'integer' }, reject: { type: 'integer' }, alt: { type: 'integer' }, missed: { type: 'integer' },
    important: { type: 'array', items: { type: 'string' }, description: '2-3 самых важных расхождения с редактором' },
  },
  required: ['scenes', 'accept', 'reject', 'alt', 'missed', 'important'],
}

const tag = c => `${c[0]}${c.length > 1 ? '+' + (c.length - 1) : ''}`
const list = c => c.map(s => '`' + s + '`').join(', ')

const results = await pipeline(
  ITEMS,
  it => it.done ? Promise.resolve({ scenes: it.chunk, resumed: true }) : agent(
    `Прочитай и выполни задание из файла /home/user/ace_attorney_investigations_translate_to_RU/work/proofread-2026-11/editor.md — это полная инструкция редактора.

Дело ${CASE}. Твоя порция — сцены по порядку: ${list(it.chunk)}.
${it.prev ? `Сцена перед порцией (для связности, только прочитать): \`${it.prev}\`.` : 'Это начало дела.'}
Каталог выдачи: \`${DIR}\` (создай, если нет). На каждую сцену порции — три файла (patch, why, questions), даже если правок нет. Пиши файлы сцены сразу, как закончишь её, не копи до конца порции.
Файлы других сцен и work/case*.json не трогай. Параллельно с тобой работают другие редакторы над другими сценами.

Верни сводку по схеме.`,
    { label: `ред:${tag(it.chunk)}`, phase: 'Редактура', schema: SUMMARY }),
  (ed, it) => agent(
    `Прочитай и выполни задание из файла /home/user/ace_attorney_investigations_translate_to_RU/work/proofread-2026-11/reviewer.md — это полная инструкция ревьюера.

Дело ${CASE}. Сцены: ${list(it.chunk)}. Каталог: \`${DIR}\` — там файлы редактора <сцена>.patch.json и <сцена>.why.json.
На каждую сцену — свой <сцена>.review.json (даже если патч пустой: {"verdicts": {}, "missed": {...}}). Пиши файл сцены сразу, как закончишь её.
Сторону границы обращения проверяй по плашке говорящего из пакета (scene_dump показывает имя), а не по номеру блока; сверяй с копиями через python3 tools/copies.py "<id>".
Чужие файлы и work/case*.json не трогай.

Верни сводку по схеме.`,
    { label: `рев:${tag(it.chunk)}`, phase: 'Ревью', schema: REVIEW })
      .then(rv => ({ chunk: it.chunk, editor: ed, review: rv })),
)

return results.filter(Boolean)
