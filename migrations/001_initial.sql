CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id BIGINT NOT NULL PRIMARY KEY,
    thread_id BIGINT NOT NULL,
    timezone_type ENUM('IANA','FIXED') NOT NULL DEFAULT 'IANA',
    timezone_value VARCHAR(64) NOT NULL DEFAULT 'UTC',
    daily_time TIME NOT NULL DEFAULT '08:00:00',
    weekly_time TIME NOT NULL DEFAULT '21:00:00',
    bound_at DATETIME NOT NULL,
    last_report_end_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    KEY idx_chat_thread (chat_id, thread_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bible_books (
    id SMALLINT NOT NULL PRIMARY KEY,
    name_ru VARCHAR(80) NOT NULL,
    abbreviation VARCHAR(32) NOT NULL,
    api_slug VARCHAR(80) NOT NULL UNIQUE,
    chapters_count SMALLINT NOT NULL,
    testament ENUM('ВЗ','НЗ') NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS reading_history (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    thread_id BIGINT NOT NULL,
    book_id SMALLINT NOT NULL,
    next_chapter SMALLINT NOT NULL,
    status ENUM('ACTIVE','PAUSED','COMPLETED','REPLACED') NOT NULL,
    next_due_at DATETIME NULL,
    started_at DATETIME NOT NULL,
    completed_at DATETIME NULL,
    replaced_at DATETIME NULL,
    KEY idx_current_reading (chat_id, thread_id, status),
    CONSTRAINT fk_reading_book FOREIGN KEY (book_id) REFERENCES bible_books(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bible_cache (
    book_id SMALLINT NOT NULL,
    chapter SMALLINT NOT NULL,
    version VARCHAR(32) NOT NULL,
    verses_json JSON NOT NULL,
    copyright_text TEXT NULL,
    etag VARCHAR(255) NULL,
    fetched_at DATETIME NOT NULL,
    PRIMARY KEY (book_id, chapter, version),
    CONSTRAINT fk_cache_book FOREIGN KEY (book_id) REFERENCES bible_books(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT NOT NULL PRIMARY KEY,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NULL,
    username VARCHAR(255) NULL,
    last_seen_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS message_metrics (
    chat_id BIGINT NOT NULL,
    thread_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    sent_at DATETIME NOT NULL,
    edited_at DATETIME NULL,
    word_count INT NOT NULL,
    i_count INT NOT NULL,
    thought_count TINYINT NOT NULL,
    question_count TINYINT NOT NULL,
    gratitude_count INT NOT NULL,
    night_count TINYINT NOT NULL,
    morning_count TINYINT NOT NULL,
    PRIMARY KEY (chat_id, message_id),
    KEY idx_metrics_period (chat_id, thread_id, sent_at),
    KEY idx_metrics_user_period (chat_id, thread_id, user_id, sent_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_totals (
    chat_id BIGINT NOT NULL,
    thread_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    message_count BIGINT NOT NULL DEFAULT 0,
    word_count BIGINT NOT NULL DEFAULT 0,
    thought_count BIGINT NOT NULL DEFAULT 0,
    i_count BIGINT NOT NULL DEFAULT 0,
    question_count BIGINT NOT NULL DEFAULT 0,
    gratitude_count BIGINT NOT NULL DEFAULT 0,
    night_count BIGINT NOT NULL DEFAULT 0,
    morning_count BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, thread_id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS publications (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    thread_id BIGINT NOT NULL,
    publication_type ENUM('CHAPTER','REPORT') NOT NULL,
    book_id SMALLINT NULL,
    chapter SMALLINT NULL,
    period_start DATETIME NULL,
    period_end DATETIME NULL,
    status ENUM('PENDING','SENDING','COMPLETED','UNCERTAIN','FAILED') NOT NULL,
    created_at DATETIME NOT NULL,
    completed_at DATETIME NULL,
    last_error TEXT NULL,
    UNIQUE KEY uq_chapter_publication (chat_id, thread_id, publication_type, book_id, chapter),
    UNIQUE KEY uq_report_publication (chat_id, thread_id, publication_type, period_end),
    KEY idx_publication_status (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS publication_parts (
    publication_id BIGINT NOT NULL,
    part_index SMALLINT NOT NULL,
    telegram_message_id BIGINT NULL,
    status ENUM('PENDING','SENT','UNCERTAIN') NOT NULL DEFAULT 'PENDING',
    sent_at DATETIME NULL,
    PRIMARY KEY (publication_id, part_index),
    CONSTRAINT fk_parts_publication FOREIGN KEY (publication_id) REFERENCES publications(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS nomination_settings (
    chat_id BIGINT NOT NULL,
    thread_id BIGINT NOT NULL,
    nomination VARCHAR(32) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (chat_id, thread_id, nomination)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS report_history (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    thread_id BIGINT NOT NULL,
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,
    results_json JSON NOT NULL,
    created_at DATETIME NOT NULL,
    UNIQUE KEY uq_report_period (chat_id, thread_id, period_end)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
