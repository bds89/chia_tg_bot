LANGUAGE_LIST = ["russian", "english"]

russian = {"chia_stat":"Статус Chia","get_balance":"Узнать баланс",
        "den":"день","dnya":"дня","dney":"дней",
        "kolvo_popytok":"Превышено количество попыток, обратитесь к администратору",
        "need_auth":"Требуется авторизация, введите пароль:",
        "node_num": "Выберите номер NODE",
        "wrote_chat_ids":"Записал chat_ids на харвестер",
        "unauth":"Неудачная авторизация №", "ot":"от",
        "wrong_pass": "Пароль не верный, попробуйте снова (осталось",
        "help_text":"Пользуйтесь кнопками, для появления кнопок наберите любое сообщение.\n\
        Для выбора языка, наберите /language\n\
        Для переключения между нодами наберите <int> номер компьютера\n\
        Для изменения таймера Watchdog наберите /wd <int> (секунд), для отключения Watchdog наберите /wd 0.\n\
        Для изменения количества параллельных плотов наберите /parallel_plots <int>\n\
        Для выбора таблицы начала следующего плота наберите /table <int>\n\
        Для изменения настроек засева наберите /set_plot_config <int>\n\
        Для включения/отключения отображения бесшумных уведомлений наберите /notify <on/off>\n\
        Для просмотра журнала watchdog наберите /log <float> (часов)\n\
        Для удаления директорий из чиа в которых нет плотов и добавления директорий в которых найдены плоты наберите /check_plots_dirs 1\n\
        Для перезапуска харвестера наберите /harvester_restart 1\n\
        Для поиска оптимального значения power_limit из диапазона [min-max] наберите /auto_power <min> <max>\n\
        Для наблюдением за количеством плотов прошедших фильтр наберите /filter <int> (>= количества плотов прошедших фильтр)\n\n\
        Не все плоты могут быть отменены. При засеве разных плотов с одинаковыми параметрами, бот не сможет найти и закрыть определенный процесс chia\
        Для корректной работы кнопок при создании плота, из-за ограничений Telegram, абсолютный путь к корню ваших дисков не должен превышать 52 байта UTF-8(52 символа для латинского алфавита)",
        "time_to_win":"Расчетное время выигрыша: ","now_plots":"Текущие плоты:","avg_time":"Среднее время на GiB:",
        "left_to_plot":"Осталось засеять:","za":"за","avg_otklik":"Среднее время отклика:","popyts":"с., попыток в логе:",
        "off_autoplot":"Откл автозасев","on_autoplot":"Вкл автозасев","cancel":"Отмена","create":"Создать","SWAP_off":"Откл.SWAP","SWAP_on":"Вкл.SWAP", "SWAP_on_on_demand":"Включил SWAP. ",
        "move":"Переместить","SWAP_size":"Размер файла SWAP:","not_ploted":"Я ничего не сеял",
        "no_file_plot":"Не нашел файла с плотами","choose_plot_cancel":"Выберите плот для отмены:",
        "cant_dell_plot":"Не могу удалить этот плот. Его команда совпадает с командой другого плота, не смогу закрыть процес chia",
        "cant_dell_files":"Не смог удалить файлы из","complete":"Завершил","procs":"процесса","deleted":"Удалил","files_in":"файлов в", "log_file":"лог-файл","plots_file":"запись из plots_file.sys",
        "anybody_create":" уже создает плот, подождите","clear_params":"Сбросил параметры","ch_size_plot":"Выберите размер плота:",
        "temp_disk":"Выберите диск для temp папки:","not_enought_space":"На ваших дисках не достаточно свободного места",
        "temp2_disk":"Выберите диск для temp2 папки:","dest_disc":"Выберите диск для конечной папки:",
        "creating":"Создаю плот...","create_ask":"Создаю плот?","choose_dell_disk":"Выберите диск c которого хотите удалить:",
        "age_plots":"Выберите возраст плотов:","old":"Старые(not NFT)","any":"Любые","no_plots_on_disk":"Не нашел плотов на этом диске",
        "type_plot":"Выберите тип плота","find":"Нашел","plots":"плотов","kolvo_to_dell":"Выберите количество плотов для удаления:",
        "no_good_plots":"На диске нет подходящих плотов","plot_of_size":"плотов размером","from_disc":"с диска",
        "on":"на:","old2":"старые:","size":"размер:","num":"количество:","will_dell":"Удаляем?","alredy_move":" уже начинает перемещение, подождите",
        "choose_disk_to_move":"Выберите диск c которого хотите переместить:","not_find_plots":"Не нашел плотов на этом диске",
        "alredy_moving":"Уже идет перемещение с этого диска",
        "num_plots_to_move":"Выберите количество плотов которое хотите переместить:",
        "choose_disk_to_move_on":"Выберите диск на который хотите переместить:",
        "not_enought_space_to_move":"На ваших дисках не достаточно места, для перемещения",
        "moving":"Начинаю перемещение...","will_send_notify":"По завершению пришлю уведомление",
        "from":"из:","to":"в:","will_move":"Начинаю перемещение?",
        "choose_disc_for_info":"Выберите диск для более подробной информации", "back":"Назад",
        "disc":"Диск: ","calc_by_total":"Расчет исходя из емкости диска:","calc_by_free":"Расчет исходя из свободного",
        "space":"места:","not_enought_space_on_disc":"Не достаточно свободного места для создания плота",
        "find_on_disc":"Нашел на диске:", "using_SATA_as_SSD":"Использую SATA как SSD","not_using_SATA_as_SSD":"Не использую SATA как SSD",
        "using_k33":"Использую K33 плоты","not_using_k33":"Не использую K33 плоты",
        "hacking_by":"Подозрительная активность от","working":"Выполняю...","you_sure":"Вы уверены?", "yes": "Да",
        "refreshed":"Обновлено:","cant_on_twice":"Не могу включить дважды","autoplot_turn_on":"Включил автозасев",
        "cant_off_twice":"Не могу отключить дважды","autoplot_turn_off":"Выключил автозасев",
        "was":"было","too_often":"Слишком часто, могу опрашивать не чаще 60 секунд",
        "set_refresh_interval":"Установил интервал обновления: ","wd_off":"Отключил Watchdog",
        "current":"Текущее значение: ","type":"Набери: ","paral_diap":"Диапазон от 1 до 30",
        "num_paral_plots":"Число параллельных плотов: ","table_diap":"Диапазон от 1 до 7",
        "start_at_table":"Начало следующего плота на таблице: ","use_SATA":"Использовать SATA",
        "not_use_SATA":"Не использовать SATA","use_K33":"Использовать K33","not_use_K33":"Не использовать K33",
        "plotting_config":"Настройки засева:","paral_plots":"Параллельных плотов:","start_table":"Таблица начала плота:",
        "using_sata_as_ssd":"Использование SATA для засева:",
        "notify_stat_for":"Статус уведомлений для","now":"теперь","unknown_user":"Я вас не знаю",
        "num_must_be_posit":"Число должно быть положительным","filter_stat":"Статус уведомлений фильтра для",
        "dirs_not_change":"Список директорий не именился",
        "for_dell_dirs_type":"Для удаления директорий, в которых нет плотов и добавления директорий в которых я найду плоты, набери: /check_plots_dirs 1",
        "filter":"Фильтр:", "proofs":"Доказательств:", "ping":"Отклик:",
        "wrong_num":"Неправильный номер","no_data":"Нет данных","decrease_plot_num":"Уменьшилось количество плотов с ","on":"до",
        "check_discs":"проверьте диски","proof_find":"Найдено доказательство! в:","long_ping":"Долгий отклик от плота:",
        "filter_pass":"сек. Фильтр прошли:","wallet_in":"Пополнение кошелька на:","sec":"сек.",
        "no_plotted":"Ничего не сеялось","not_find_plot_file":"Не нашел файла с плотами","clear_plot":"Очистка плота:",
        "files_in":"файлов в","cant_dell_files_from":"Не смог удалить файлы из","dell_log_in":"Удалил лог файл в",
        "start_text":"Выберите действие:\n/language\n/wd <секунд>\n/parallel_plots <int>; /table <int>\n/set_plot_config; \n/notify <on/off>; /filter <int>\n/check_plots_dirs 1\n/log <float> (часов)\n/harvester_restart 1\n/auto_power <min> <max>",
        "start_bot":"Бот запущен. Проверьте, возможно было отключение электричества",
        "start_with_params":"Запуск c параметрами","start_without_params":"Запуск без параметров",
        "cancel_dell_plots":"Сейчас произойдет очистка недосозданных плотов, нажмите ctrl+с для отмены",
        "finished_move":"Закончил перемещение:", "plots_from":"плотов из", "time_done":"Время выполнения:",
        "apply_lang":"Выбран русский язык","no_data_from_trex":"Нет ответа от T-Rex","gpu_difficulty": "Сложность",
        "hashrate":"Хэшрейт","hashrate_day":"Хэшрейт за день","gpu_id":"GPU ID","gpu_name":"GPU NAME","gpu_fan_speed":"Fan","gpu_power":"Мощность",
        "gpu_temperature":"Температура","gpu_invalid_count":"gpu_invalid_count","binance_balances":"Балансы Binance", "okex_balances":"Балансы OKEX", "not_enought_mon":"Не достаточно",
        "for_sell_req":"для продажи, требуется", "current_governor":"Текущий говернор", "set_governor":"Установил", 
        "for_restart_harvester":"Для перезагрузки харвестера наберите /harvester_restart 1", "plot_not_response": "остановился засев плота",
        "auto_power_fail":"Не смог найти оптимальную мощность", "auto_power_done":"Оптимальная мощность найдена", "auto_power_start":"Ищу оптимальную мощность, ожидайте уведомления",
        "for_set_win_progress":"Для установки прогресса до выигрыша в процентах наберите /set_win_progress <float>"}

english = {'chia_stat': 'Chia status', 'get_balance': 'Show balance', 'den': 'day', 'dnya': 'days', 'dney': 'days', 
        'kolvo_popytok': 'The number of attempts exceeded, contact the administrator', 'need_auth': 'Authorization is required, enter the password:', 
        'node_num': 'Select Node number', 'wrote_chat_ids': 'Recorded Chat_ids of harvester', 'unauth': 'Unsuccessful authorization number', 'ot': 'by', 
        'wrong_pass': 'Password is not true, try again (it remains', 'help_text': 
        'Use the buttons to appear the buttons to type any message.\n\
        To select a language, dial /language\n\
        To switch between nods, dial <int> Computer number\n\
        To change the WatchDog timer, dial /wd <int> (seconds), to disable WatchDog dial /wd 0.\n\
        To change the number of parallel plots, dial /parallel_plots <int>\n\
        To select the table of the beginning of the next plot, dial /table <int>\n\
        To change sowing settings, dial /set_plot_config <int>\n\
        To enable / disable the display of silent notifications, dial /notify <ON / OFF>\n\
        To view the WatchDog log, dial /log <Float> (hours)\n\
        To remove directories from Chia in which there are no plots and add directories in which the plots are found dial /check_plots_dirs 1\n\
        To restart harvester, type /harvester_restart 1\n\
        To find the optimal power_limit value from the range [min-max], type /auto_power <min> <max>\n\
        For observation of the number of plots of the past filter, dial / filter <int> (> = quantities of the plots of the past filter)\n\n\
        Not all plots can be canceled. When sowing different plots with the same parameters, the bot will not be able to find and close a specific CHIA process for correct operation of the buttons when creating a fleet, due to the restrictions of Telegram, the absolute path to the root of your disks should not exceed 52 bytes UTF-8 (52 characters for Latin alphabet)', 
        'time_to_win': 'Estimated winning time:', 'now_plots': 'Current plots:', 'avg_time': 'Average time on GIB:', 'left_to_plot': 'It remains to done plotting:', 
        'za': 'for', 'avg_otklik': 'Average response time:', 'popyts': 's., Attempts in the log:', 'off_autoplot': 'Off autoploting', 'on_autoplot': 'ON autoploting', 
        'cancel': 'Cancel', 'create': 'Create', 'SWAP_off': 'SWAP off', 'SWAP_on': 'SWAP on', 'move': 'Move', 'SWAP_size': 'Size file SWAP:', "SWAP_on_on_demand":"Enabled SWAP. ",
        'not_ploted': 'I did not sow anything', 'no_file_plot': 'Did not find a file with plots', 'choose_plot_cancel': 'Choose a plot to cancel:', 
        'cant_dell_plot': 'I can not remove this plot.His team coincides with the team of another fleet, I can not close the process chia', 
        'cant_dell_files': 'I could not delete files from', 'complete': 'Completed', 'procs': 'Process', 'deleted': 'Removal', 'files_in': 'files in', 
        'log_file': 'Log file.', 'plots_file': 'Record from plots_file.sys', 'anybody_create': 'already creates a plot, wait', 'clear_params': 'Passed Parameters', 
        'ch_size_plot': 'Select the size of the plot:', 'temp_disk': 'Select a disc for Temp folder:', 'not_enought_space': 'On your disks is not enough free space', 
        'temp2_disk': 'Select a disc for Temp2 folders:', 'dest_disc': 'Select a disk for the final folder:', 'creating': 'Create a plot ...', 
        'create_ask': 'Create a plot?', 'choose_dell_disk': 'Select the disk from which you want to delete:', 'age_plots': 'Choose the age of plots:', 
        'old': 'Old (Not NFT)', 'any': 'Any', 'no_plots_on_disk': 'Did not find the plots on this disk', 'type_plot': 'Select the type of plot', 
        'find': 'Found', 'plots': 'pledge', 'kolvo_to_dell': 'Select the number of plots to remove:', 'no_good_plots': 'There are no suitable plots on the disk.', 
        'plot_of_size': 'pledge', 'from_disc': 'From disk', 'on': 'to', 'old2': 'Old:', 'size': 'the size:', 'num': 'amount:', 'will_dell': 'Remove?', 
        'alredy_move': 'already starts moving, wait', 'choose_disk_to_move': 'Select the disk from which you want to move:', 
        'not_find_plots': 'Did not find the plots on this disk', 'alredy_moving': 'Already moving from this disk', 'num_plots_to_move': 'Select the number of plots you want to move:', 
        'choose_disk_to_move_on': 'Select the disk to which you want to move:', 'not_enought_space_to_move': 'On your disks is not enough space for moving', 
        'moving': 'I start moving ...', 'will_send_notify': 'Upon completion, send a notice', 'from': 'from:', 'to': 'in:', 'will_move': 'Start moving?', 
        'choose_disc_for_info': 'Select a disk for more details.', 'back': 'Back', 'disc': 'Disk:', 'calc_by_total': 'Calculation based on the disk capacity:', 
        'calc_by_free': 'Calculation based on free', 'space': 'Places:', 'not_enought_space_on_disc': 'Not enough free space to create a plot', 
        'find_on_disc': 'Found on the disk:', 'using_SATA_as_SSD': 'I use SATA as SSD', 'not_using_SATA_as_SSD': 'I do not use SATA like SSD', 
        'using_k33': 'I use k33 plots', 'not_using_k33': 'I do not use K33 plots', 'hacking_by': 'Suspicious activity OT', 'working': 'Perform ...', 
        'you_sure': 'Are you sure?', 'yes': 'Yes', 'refreshed': 'Updated:', 'cant_on_twice': 'I can not turn on twice', 'autoplot_turn_on': 'Included Avtozashev', 
        'cant_off_twice': 'I can not turn off twice', 'autoplot_turn_off': 'Turn off the auto site', 'was': 'It was', 
        'too_often': 'Too often, I can interview no more than 60 seconds', 'set_refresh_interval': 'Installed update interval:', 
        'wd_off': 'Disabled Watchdog.', 'current': 'Present value:', 'type': 'Charge:', 'paral_diap': 'Range from 1 to 30', 'num_paral_plots': 'The number of parallel plots:', 
        'table_diap': 'Range from 1 to 7', 'start_at_table': 'The beginning of the next air on the table:', 'use_SATA': 'Use SATA', 'not_use_SATA': 'Do not use SATA', 
        'use_K33': 'Use K33.', 'not_use_K33': 'Do not use K33', 'plotting_config': 'Sour Settings:', 'paral_plots': 'Parallel plots:', 'start_table': 'Table of start of the plot:', 
        'using_sata_as_ssd': 'Using SATA for sowing:', 'notify_stat_for': 'Notification status for', 'now': 'now', 'unknown_user': 'I do not know you', 
        'num_must_be_posit': 'The number must be positive', 'filter_stat': 'Filter notification status for', 'dirs_not_change': 'The list of directories did not name', 
        'for_dell_dirs_type': 'To remove directories in which there are no plots and add directories in which I will find plots, type: / check_plots_dirs 1', 
        'filter': 'Filter:', 'proofs': 'Evidence:', 'ping': 'Response:', 'wrong_num': 'Wrong number', 'no_data': 'No data', 
        'decrease_plot_num': 'Decreased the number of plots with', 'check_discs': 'Check discs', 'proof_find': 'Found proof!in:', 
        'long_ping': 'Long response from the plot:', 'filter_pass': 'sec.The filter passed:', 'wallet_in': 'Replenishment of the wallet on:', 'sec': 's.', 
        'no_plotted': 'Nothing was sown', 'not_find_plot_file': 'Did not find a file with plots', 'clear_plot': 'Cleaning the countertop:', 
        'cant_dell_files_from': 'I could not delete files from', 'dell_log_in': 'Removed log file in', 'start_text': 
        'Choose an action:\n/language\n/wd <seconds>\n/parallel_plots <int>; /table <int>\n/set_plot_config; \n/notify <on/off>; /filter <int>\n/check_plots_dirs 1\n/log <float> (hours)\n/harvester_restart 1\n/auto_power <min> <max>', 
        'start_bot': 'Bot is running.Check, it may have been disconnected electricity', 'start_with_params': 'Launch with parameters', 
        'start_without_params': 'Running without parameters', 'cancel_dell_plots': 'There will now be cleaned by false plots, press Ctrl + C to cancel', 
        'finished_move': 'Finished moving:', 'plots_from': 'plots out', 'time_done': 'Lead time:',
        "apply_lang":"English is selected","no_data_from_trex":"No response from T-Rex","gpu_difficulty": "Difficulty",
        "hashrate":"Hashrate","hashrate_day":"Hashrate day","gpu_id":"GPU ID","gpu_name":"GPU NAME","gpu_fan_speed":"Fan","gpu_power":"Power",
        "gpu_temperature":"Temperature","gpu_invalid_count":"gpu_invalid_count","binance_balances":"Binance balances", "okex_balances":"OKEX balances", "not_enought_mon":"Not enought",
        "for_sell_req":"for sell, requried", "current_governor":"Сurrent governor", "set_governor":"Set",
        "for_restart_harvester": "To restart harvester, type /harvester_restart 1", "plot_not_response": "plotting this plot was stoped",
        "auto_power_fail":"Couldn't find optimal power", "auto_power_done":"Optimum power found", "auto_power_start":"Looking for optimal power, wait for notification",
        "for_set_win_progress":"To set the progress to the percentage gain, type /set_win_progress <float>"} 