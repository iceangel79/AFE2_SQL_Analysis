-- Synthetischer Mini-Dump fuer Tests (keine echten Daten)
CREATE TABLE `wp_matomo_log_action` (
  `idaction` int UNSIGNED NOT NULL,
  `name` varchar(4096) DEFAULT NULL,
  `hash` int UNSIGNED NOT NULL,
  `type` tinyint UNSIGNED DEFAULT NULL,
  `url_prefix` tinyint DEFAULT NULL
) ENGINE=InnoDB;

INSERT INTO `wp_matomo_log_action` (`idaction`, `name`, `hash`, `type`, `url_prefix`) VALUES
(1, 'example.ch/', 1, 1, 2),
(2, 'example.ch/one-pager/', 2, 1, 2),
(3, 'example.ch/kontakt/', 3, 1, 2),
(4, 'div#a > p', 4, 96, NULL),
(5, 'div#b > img', 5, 96, NULL),
(6, 'It\'s a \"test\"\n', 6, 4, NULL);

CREATE TABLE `wp_matomo_log_hsr` (
  `idloghsr` int UNSIGNED NOT NULL,
  `idsite` int UNSIGNED NOT NULL,
  `idvisit` bigint UNSIGNED NOT NULL,
  `idhsrview` char(6) NOT NULL,
  `idpageview` char(6) DEFAULT NULL,
  `idaction_url` int UNSIGNED NOT NULL DEFAULT '0',
  `device_type` tinyint(1) NOT NULL DEFAULT '1',
  `server_time` datetime NOT NULL,
  `time_on_page` bigint UNSIGNED NOT NULL,
  `viewport_w_px` smallint UNSIGNED DEFAULT '0',
  `viewport_h_px` smallint UNSIGNED DEFAULT '0',
  `scroll_y_max_relative` smallint UNSIGNED DEFAULT '0',
  `fold_y_relative` smallint UNSIGNED DEFAULT '0'
) ENGINE=InnoDB;

INSERT INTO `wp_matomo_log_hsr` (`idloghsr`, `idsite`, `idvisit`, `idhsrview`, `idpageview`, `idaction_url`, `device_type`, `server_time`, `time_on_page`, `viewport_w_px`, `viewport_h_px`, `scroll_y_max_relative`, `fold_y_relative`) VALUES
(1, 1, 10, 'aaaaaa', 'bbbbbb', 1, 1, '2026-11-02 10:00:00', 10000, 1700, 1200, 1000, 800),
(2, 1, 10, 'cccccc', 'dddddd', 3, 1, '2026-11-02 10:00:10', 5000, 1700, 1200, 500, 800),
(3, 1, 11, 'eeeeee', 'ffffff', 2, 1, '2026-11-02 11:00:00', 20000, 1700, 1200, 900, 300),
(4, 1, 12, 'gggggg', 'hhhhhh', 2, 1, '2026-10-20 09:00:00', 1000, 1700, 1200, 100, 300),
(5, 1, 12, 'iiiiii', 'jjjjjj', 1, 1, '2026-10-20 09:00:01', 1000, 1700, 1200, 100, 300),
(6, 1, 13, 'kkkkkk', 'llllll', 1, 3, '2026-11-02 12:00:00', 3000, 360, 640, 100, 300);

CREATE TABLE `wp_matomo_log_hsr_event` (
  `idhsrevent` bigint UNSIGNED NOT NULL,
  `idloghsr` int UNSIGNED NOT NULL,
  `time_since_load` bigint UNSIGNED NOT NULL DEFAULT '0',
  `event_type` tinyint UNSIGNED NOT NULL DEFAULT '0',
  `idselector` int UNSIGNED DEFAULT NULL,
  `x` smallint NOT NULL DEFAULT '0',
  `y` smallint NOT NULL DEFAULT '0',
  `idhsrblob` int UNSIGNED DEFAULT NULL
) ENGINE=InnoDB;

INSERT INTO `wp_matomo_log_hsr_event` (`idhsrevent`, `idloghsr`, `time_since_load`, `event_type`, `idselector`, `x`, `y`, `idhsrblob`) VALUES
(1, 1, 0, 1, 4, 100, 100, NULL),
(2, 1, 200, 1, 4, 300, 100, NULL),
(3, 1, 400, 1, 4, 100, 100, NULL),
(4, 1, 600, 1, 4, 300, 100, NULL),
(5, 1, 3000, 1, 5, 500, 500, NULL),
(6, 1, 3200, 2, 5, 500, 500, NULL),
(7, 2, 1500, 10, NULL, 0, 0, 1),
(8, 3, 100, 3, NULL, 0, 100, NULL),
(9, 3, 300, 3, NULL, 0, 300, NULL),
(10, 3, 500, 3, NULL, 0, 200, NULL),
(11, 3, 900, 9, NULL, 0, 0, 1);

CREATE TABLE `wp_matomo_log_hsr_blob` (
  `idhsrblob` int UNSIGNED NOT NULL,
  `hash` int UNSIGNED NOT NULL,
  `compressed` tinyint UNSIGNED NOT NULL DEFAULT '0',
  `value` mediumblob
) ENGINE=InnoDB;

INSERT INTO `wp_matomo_log_hsr_blob` (`idhsrblob`, `hash`, `compressed`, `value`) VALUES
(1, 1, 1, 0x789c33040000320032);

CREATE TABLE `wp_matomo_log_visit` (
  `idvisit` bigint UNSIGNED NOT NULL,
  `idsite` int UNSIGNED NOT NULL,
  `idvisitor` binary(8) NOT NULL,
  `location_ip` varbinary(16) NOT NULL,
  `config_browser_name` varchar(40) DEFAULT NULL,
  `location_city` varchar(255) DEFAULT NULL
) ENGINE=InnoDB;

INSERT INTO `wp_matomo_log_visit` (`idvisit`, `idsite`, `idvisitor`, `location_ip`, `config_browser_name`, `location_city`) VALUES
(10, 1, 0x0102030405060708, 0xc0a80000, 'CH', 'Zuerich'),
(11, 1, 0x0102030405060709, 0xc0a80000, 'FF', NULL);

CREATE TABLE `wp_users` (
  `ID` bigint UNSIGNED NOT NULL,
  `user_pass` varchar(255) NOT NULL
) ENGINE=InnoDB;

INSERT INTO `wp_users` (`ID`, `user_pass`) VALUES
(1, '$P$geheim;mit;semikolon');
