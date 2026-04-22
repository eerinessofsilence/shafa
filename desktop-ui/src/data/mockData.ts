import type {
  AlertItem,
  ChartPoint,
  LogRecordItem,
  Metric,
  NavItem,
  NoteItem,
  ParserQueueItem,
  ParserResult,
  SettingToggle,
  SettingsGroup,
  StatusItem,
} from '../types';

export const navItems: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', caption: 'Обзор и сигналы' },
  { id: 'accounts', label: 'Аккаунты', caption: 'Каталог и детали' },
  { id: 'logs', label: 'Логи', caption: 'События и runtime' },
  { id: 'settings', label: 'Настройки', caption: 'Системные параметры' },
];

export const dashboardMetrics: Metric[] = [
  {
    kind: 'accounts',
    label: 'Средняя скорость',
    value: '14.2',
    unit: '/мин',
    badge: '+8%',
    badgeTone: 'teal',
    accent: 'teal',
  },
  {
    kind: 'items',
    label: 'Обработано за 7 дней',
    value: '1 842',
    unit: 'ед.',
    badge: '+12%',
    badgeTone: 'blue',
    accent: 'blue',
  },
  {
    kind: 'active',
    label: 'Активные аккаунты',
    value: '5',
    unit: 'онлайн',
    badge: 'Стабильно',
    badgeTone: 'neutral',
    accent: 'amber',
  },
  {
    kind: 'errors',
    label: 'Баны / таймауты',
    value: '3',
    unit: 'лог.',
    badge: '-5%',
    badgeTone: 'rose',
    accent: 'rose',
  },
];

export const systemStatus: StatusItem[] = [
  {
    label: 'Пиковый день',
    value: 'Пятница дала 171 публикацию и 7 ошибок на моковой неделе.',
    badge: 'Peak',
    tone: 'success',
  },
  {
    label: 'Базовая нагрузка',
    value: 'Основной объём держится в диапазоне 118-156 публикаций в день.',
    badge: 'Flow',
    tone: 'info',
  },
  {
    label: 'Зона риска',
    value: '3 бана и 11 таймаутов пока показываем как отдельный моковый блок.',
    badge: 'Watch',
    tone: 'warning',
  },
];

export const dashboardAlerts: AlertItem[] = [
  {
    title: 'Нужен редизайн detail-панели',
    copy: 'Авторизация, каналы и действия с сессиями должны разойтись по отдельным блокам.',
    tone: 'warning',
  },
  {
    title: 'Dashboard теперь с полезной нагрузкой',
    copy: 'Большой пустой placeholder заменен на живой графический блок и карточки сигналов.',
    tone: 'info',
  },
  {
    title: 'Текущий слой данных моковый',
    copy: 'Подключение Python backend можно сделать отдельно без переделки визуального shell.',
    tone: 'success',
  },
];

export const releaseNotes: NoteItem[] = [
  {
    title: 'Electron shell',
    copy: 'Отдельная desktop-оболочка без конфликта с текущим PySide6 приложением.',
  },
  {
    title: 'React navigation',
    copy: 'Все основные страницы уже вынесены в компонентную структуру с единым стилем.',
  },
  {
    title: 'Static mock data',
    copy: 'Никаких запросов, только шаблонный UI для следующего шага интеграции.',
  },
];

export const settingToggles: SettingToggle[] = [
  {
    label: 'Случайная задержка',
    copy: 'Добавлять джиттер при проходе по страницам.',
    enabled: true,
  },
  {
    label: 'Сохранять raw JSON',
    copy: 'Отдельный тумблер для дебага и анализа фейлов.',
    enabled: false,
  },
];

export const parserQueue: ParserQueueItem[] = [
  {
    title: 'Категория A',
    copy: '12 страниц, 2.5 сек, старт через 4 мин',
    badge: 'queued',
    tone: 'warning',
  },
  {
    title: 'Категория B',
    copy: 'Пауза до ручного подтверждения',
    badge: 'idle',
    tone: 'neutral',
  },
  {
    title: 'Категория C',
    copy: 'Последний прогон завершен успешно',
    badge: 'done',
    tone: 'success',
  },
];

export const parserResults: ParserResult[] = [
  {
    id: '1',
    title: 'Льняной пиджак',
    price: '1 850 грн',
    meta: 'XS-S, отличное состояние',
  },
  {
    id: '2',
    title: 'Кожаные ботинки',
    price: '2 640 грн',
    meta: '39 размер, premium feed',
  },
  {
    id: '3',
    title: 'Плиссированная юбка',
    price: '1 140 грн',
    meta: 'M, womenswear stream',
  },
  {
    id: '4',
    title: 'Винтажная сумка',
    price: '3 900 грн',
    meta: '1/1, curated selection',
  },
];

export const logRecords: LogRecordItem[] = [
  {
    time: '10:14:02',
    account: 'шляпа',
    level: 'SUCCESS',
    tone: 'success',
    message:
      'Сохранено 12 новых элементов, каналы экспортированы в runtime-конфиг.',
  },
  {
    time: '10:17:48',
    account: 'linen',
    level: 'ERROR',
    tone: 'danger',
    message:
      'Telegram auth process завершился с ошибкой, нужен повторный запуск кода.',
  },
  {
    time: '10:20:15',
    account: 'waffle',
    level: 'INFO',
    tone: 'info',
    message: 'Переключение на ветку main прошло без обновления зависимостей.',
  },
  {
    time: '10:22:09',
    account: 'щляпчик',
    level: 'INFO',
    tone: 'neutral',
    message:
      'Сессия Shafa найдена и будет переиспользована при следующем запуске.',
  },
];

export const settingsGroups: SettingsGroup[] = [
  {
    title: 'Общие параметры',
    subtitle: 'Базовые пути и режим приложения',
    fields: [
      { label: 'Режим', value: 'clothes' },
      { label: 'Папка данных', value: '/Users/eeri/.../data' },
      { label: 'Proxy file', value: '/Users/eeri/.../proxy.txt' },
      { label: 'Интервал refresh', value: '30 сек' },
    ],
  },
  {
    title: 'Desktop оболочка',
    subtitle: 'Что уже настроено в шаблоне',
    fields: [
      { label: 'Renderer', value: 'React + Vite' },
      { label: 'Shell', value: 'Electron' },
      { label: 'Источник данных', value: 'Mock data only' },
      { label: 'Статус интеграции', value: 'UI prototype' },
    ],
  },
];

export const dashboardSeries: ChartPoint[] = [
  { date: '2026-04-13', label: 'Пн', items: 102, errors: 6 },
  { date: '2026-04-14', label: 'Вт', items: 124, errors: 4 },
  { date: '2026-04-15', label: 'Ср', items: 118, errors: 3 },
  { date: '2026-04-16', label: 'Чт', items: 146, errors: 5 },
  { date: '2026-04-17', label: 'Пт', items: 171, errors: 7 },
  { date: '2026-04-18', label: 'Сб', items: 132, errors: 4 },
  { date: '2026-04-19', label: 'Вс', items: 156, errors: 3 },
];
