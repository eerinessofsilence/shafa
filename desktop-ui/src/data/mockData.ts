import type {
  AccountRow,
  AlertItem,
  ChartPoint,
  LogRecordItem,
  Metric,
  NavItem,
  NoteItem,
  ParserQueueItem,
  ParserResult,
  ParserToggle,
  SettingsGroup,
  StatusItem,
} from '../types';

export const navItems: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', caption: 'Обзор и сигналы' },
  { id: 'accounts', label: 'Аккаунты', caption: 'Каталог и детали' },
  { id: 'parsing', label: 'Парсинг', caption: 'Запуск и очередь' },
  { id: 'stats', label: 'Статистика', caption: 'Графики и KPI' },
  { id: 'settings', label: 'Настройки', caption: 'Системные параметры' },
];

export const dashboardMetrics: Metric[] = [
  { label: 'Всего аккаунтов', value: '12', accent: 'teal' },
  { label: 'Активные аккаунты', value: '5', accent: 'amber' },
  { label: 'Всего товаров', value: '284', accent: 'blue' },
  { label: 'Всего ошибок', value: '7', accent: 'rose' },
];

export const systemStatus: StatusItem[] = [
  {
    label: 'Основной pipeline',
    value: 'Работает стабильно',
    badge: 'Good',
    tone: 'success',
  },
  {
    label: 'Telegram login flow',
    value: '1 сессия ожидает код',
    badge: 'Wait',
    tone: 'warning',
  },
  {
    label: 'Очередь задач',
    value: '8 заданий на подготовке',
    badge: 'Queue',
    tone: 'info',
  },
  {
    label: 'Локальное состояние',
    value: 'Все mock-данные на месте',
    badge: 'Static',
    tone: 'neutral',
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

export const accountRows: AccountRow[] = [
  {
    id: 'waffle',
    name: 'waffle',
    path: '/workspace/shafa/main',
    branch: 'main',
    browser: 'Нет',
    timer: '5 мин',
    errors: '2',
    statusLabel: 'stopped',
    statusTone: 'neutral',
    telegramChannels: [
      {
        id: 'wardrobe-drop',
        title: 'Wardrobe Drop',
        handle: 't.me/wardrobe_drop',
        photoSource: 'Сообщение',
      },
      {
        id: 'shafa-daily',
        title: 'Shafa Daily',
        handle: 't.me/shafa_daily',
        photoSource: 'Комментарии',
      },
      {
        id: 'womenwear-mock',
        title: 'Womenwear Mock',
        handle: 't.me/womenwear_mock',
        photoSource: 'Два в одном',
      },
      {
        id: 'sales-alpha',
        title: 'Sales Alpha',
        handle: 't.me/sales_alpha',
        photoSource: 'Сообщение',
      },
    ],
  },
  {
    id: 'hat',
    name: 'шляпа',
    path: '/workspace/shafa/clothes-feature',
    branch: 'clothes-feature',
    browser: 'Да',
    timer: '8 мин',
    errors: '0',
    statusLabel: 'running',
    statusTone: 'success',
    telegramChannels: [
      {
        id: 'fashion-lab',
        title: 'Fashion Lab',
        handle: 't.me/fashion_lab',
        photoSource: 'Комментарии',
      },
      {
        id: 'premium-mock',
        title: 'Premium Mock',
        handle: 't.me/premium_mock',
        photoSource: 'Два в одном',
      },
      {
        id: 'sneaker-board',
        title: 'Sneaker Board',
        handle: 't.me/sneaker_board',
        photoSource: 'Сообщение',
      },
    ],
  },
  {
    id: 'capsule',
    name: 'щляпчик',
    path: '/workspace/shafa/sneakers',
    branch: 'sneakers-ui',
    browser: 'Нет',
    timer: '15 мин',
    errors: '1',
    statusLabel: 'checking',
    statusTone: 'warning',
    telegramChannels: [
      {
        id: 'drop-queue',
        title: 'Drop Queue',
        handle: 't.me/drop_queue',
        photoSource: 'Комментарии',
      },
      {
        id: 'streetwear-flow',
        title: 'Streetwear Flow',
        handle: 't.me/streetwear_flow',
        photoSource: 'Два в одном',
      },
      {
        id: 'runner-pairs',
        title: 'Runner Pairs',
        handle: 't.me/runner_pairs',
        photoSource: 'Сообщение',
      },
    ],
  },
  {
    id: 'linen',
    name: 'linen',
    path: '/workspace/shafa/ops',
    branch: 'ops-dashboard',
    browser: 'Да',
    timer: '12 мин',
    errors: '4',
    statusLabel: 'error',
    statusTone: 'danger',
    telegramChannels: [
      {
        id: 'backoffice-mock',
        title: 'Backoffice Mock',
        handle: 't.me/backoffice_mock',
        photoSource: 'Комментарии',
      },
      {
        id: 'archive-lane',
        title: 'Archive Lane',
        handle: 't.me/archive_lane',
        photoSource: 'Два в одном',
      },
    ],
  },
];

export const parserToggles: ParserToggle[] = [
  {
    label: 'Использовать прокси',
    copy: 'Подставлять статический пул прокси в будущий runtime.',
    enabled: true,
  },
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

export const statsMetrics: Metric[] = [
  {
    label: 'Скорость',
    value: '14.2/min',
    accent: 'teal',
  },
  {
    label: 'Обработано',
    value: '1 842',
    accent: 'blue',
  },
  {
    label: 'Баны',
    value: '3',
    accent: 'amber',
  },
  {
    label: 'Таймауты',
    value: '11',
    accent: 'rose',
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
  { label: '08', items: 14, errors: 1 },
  { label: '09', items: 18, errors: 1 },
  { label: '10', items: 24, errors: 2 },
  { label: '11', items: 31, errors: 2 },
  { label: '12', items: 27, errors: 1 },
  { label: '13', items: 35, errors: 3 },
  { label: '14', items: 30, errors: 2 },
];

export const statsSeries: ChartPoint[] = [
  { label: 'Пн', items: 102, errors: 6 },
  { label: 'Вт', items: 124, errors: 4 },
  { label: 'Ср', items: 118, errors: 3 },
  { label: 'Чт', items: 146, errors: 5 },
  { label: 'Пт', items: 171, errors: 7 },
  { label: 'Сб', items: 132, errors: 4 },
  { label: 'Вс', items: 156, errors: 3 },
];
