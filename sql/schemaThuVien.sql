SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ---------------------------------------------------------------------
-- 1. USERS - Tài khoản người dùng (đăng nhập qua Google OAuth)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
    `id`            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `google_id`     VARCHAR(64)  NOT NULL UNIQUE COMMENT 'Sub ID trả về từ Google OAuth',
    `email`         VARCHAR(255) NOT NULL UNIQUE,
    `full_name`     VARCHAR(150) NOT NULL,
    `avatar_url`    VARCHAR(500) DEFAULT NULL,
    `school`        VARCHAR(255) DEFAULT NULL COMMENT 'Trường / Khoa',
    `role`          ENUM('member', 'admin') NOT NULL DEFAULT 'member',
    `status`        ENUM('active', 'locked') NOT NULL DEFAULT 'active',
    `created_at`    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_users_role` (`role`),
    INDEX `idx_users_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- 2. CATEGORIES - Danh mục / môn học / khoá học (phân cấp)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `categories`;
CREATE TABLE `categories` (
    `id`          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `name`        VARCHAR(150) NOT NULL,
    `parent_id`   INT UNSIGNED DEFAULT NULL COMMENT 'Danh mục cha, NULL = danh mục gốc',
    `created_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_categories_parent`
        FOREIGN KEY (`parent_id`) REFERENCES `categories` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE,
    INDEX `idx_categories_parent` (`parent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- 3. DOCUMENTS - Tài liệu
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `documents`;
CREATE TABLE `documents` (
    `id`               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `uploader_id`      INT UNSIGNED NOT NULL,
    `category_id`      INT UNSIGNED DEFAULT NULL,
    `title`            VARCHAR(255) NOT NULL,
    `description`      TEXT DEFAULT NULL,
    `subject`          VARCHAR(150) DEFAULT NULL,
    `file_path`        VARCHAR(500) NOT NULL,
    `file_type`        VARCHAR(20)  DEFAULT NULL COMMENT 'pdf, docx, pptx, ...',
    `file_size`        BIGINT UNSIGNED DEFAULT NULL COMMENT 'Kích thước file (bytes)',
    `visibility`       ENUM('public', 'require_login') NOT NULL DEFAULT 'public',
    `status`           ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending',
    `view_count`       INT UNSIGNED NOT NULL DEFAULT 0,
    `download_count`   INT UNSIGNED NOT NULL DEFAULT 0,
    `avg_rating`       DECIMAL(2,1) NOT NULL DEFAULT 0.0 COMMENT 'Denormalized - tự động cập nhật bởi trigger',
    `total_ratings`    INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Tổng số lượt đánh giá - dùng để tính avg nhanh hơn',
    `created_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT `fk_documents_uploader`
        FOREIGN KEY (`uploader_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_documents_category`
        FOREIGN KEY (`category_id`) REFERENCES `categories` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE,
    INDEX `idx_documents_uploader` (`uploader_id`),
    INDEX `idx_documents_category` (`category_id`),
    INDEX `idx_documents_status` (`status`),
    INDEX `idx_documents_created_at` (`created_at`),
    FULLTEXT INDEX `ft_documents_search` (`title`, `description`, `subject`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- 4. COMMENTS - Bình luận (một chiều, không trả lời)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `comments`;
CREATE TABLE `comments` (
    `id`           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `document_id`  INT UNSIGNED NOT NULL,
    `user_id`      INT UNSIGNED NOT NULL,
    `content`      TEXT NOT NULL,
    `is_edited`    TINYINT(1) NOT NULL DEFAULT 0,
    `is_deleted`   TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Xoá mềm',
    `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT `fk_comments_document`
        FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_comments_user`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX `idx_comments_document` (`document_id`),
    INDEX `idx_comments_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- 5. RATINGS - Đánh giá sao (1 lần / thành viên / tài liệu, không sửa)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `ratings`;
CREATE TABLE `ratings` (
    `id`           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `document_id`  INT UNSIGNED NOT NULL,
    `user_id`      INT UNSIGNED NOT NULL,
    `stars`        TINYINT UNSIGNED NOT NULL COMMENT 'Giá trị 1-5',
    `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_ratings_document`
        FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_ratings_user`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `chk_ratings_stars` CHECK (`stars` BETWEEN 1 AND 5),
    UNIQUE KEY `uq_ratings_document_user` (`document_id`, `user_id`),
    INDEX `idx_ratings_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- 6. VIOLATION_REPORTS - Báo cáo vi phạm & xử lý
--    target_type/target_id là khoá đa hình (document hoặc comment).
--    Lưu ý: Không có FK cứng - cần kiểm tra tính hợp lệ ở tầng ứng dụng
--           và xử lý xóa mềm / cascade ở backend.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `violation_reports`;
CREATE TABLE `violation_reports` (
    `id`               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `reporter_id`      INT UNSIGNED NOT NULL,
    `target_type`      ENUM('document', 'comment') NOT NULL,
    `target_id`        INT UNSIGNED NOT NULL,
    `reason`           TEXT NOT NULL,
    `status`           ENUM('pending', 'resolved', 'rejected') NOT NULL DEFAULT 'pending',
    `handled_by`       INT UNSIGNED DEFAULT NULL COMMENT 'Admin xử lý',
    `resolution_note`  TEXT DEFAULT NULL,
    `created_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `resolved_at`      DATETIME DEFAULT NULL,
    CONSTRAINT `fk_reports_reporter`
        FOREIGN KEY (`reporter_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_reports_handled_by`
        FOREIGN KEY (`handled_by`) REFERENCES `users` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE,
    INDEX `idx_reports_status` (`status`),
    INDEX `idx_reports_target` (`target_type`, `target_id`),
    INDEX `idx_reports_reporter` (`reporter_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- 7. PERSONAL_LIBRARY - Thư viện cá nhân (n-n giữa user và document)
--    Lưu ý: type='uploaded' bị loại bỏ vì đã có documents.uploader_id
--           Chỉ giữ lại 'downloaded' và 'favorite'
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `personal_library`;
CREATE TABLE `personal_library` (
    `id`           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `user_id`      INT UNSIGNED NOT NULL,
    `document_id`  INT UNSIGNED NOT NULL,
    `type`         ENUM('downloaded', 'favorite') NOT NULL,
    `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_library_user`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_library_document`
        FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE KEY `uq_library_user_doc_type` (`user_id`, `document_id`, `type`),
    INDEX `idx_library_document` (`document_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- 8. DOWNLOADS - Lịch sử tải xuống (log)
--    Lưu ý: Nếu muốn mỗi user chỉ tính 1 lần tải/tài liệu, hãy thêm
--           UNIQUE(user_id, document_id) hoặc xử lý ở backend.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `downloads`;
CREATE TABLE `downloads` (
    `id`             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `user_id`        INT UNSIGNED DEFAULT NULL COMMENT 'NULL nếu khách vãng lai (nếu cho phép)',
    `document_id`    INT UNSIGNED NOT NULL,
    `ip_address`     VARCHAR(45) DEFAULT NULL COMMENT 'IPv4 hoặc IPv6',
    `downloaded_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_downloads_user`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT `fk_downloads_document`
        FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX `idx_downloads_document_time` (`document_id`, `downloaded_at`),
    INDEX `idx_downloads_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- 9. DOCUMENT_VIEWS - Lịch sử xem tài liệu (log)
--    Lưu ý: Tương tự downloads, nếu cần unique thì thêm ràng buộc.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `document_views`;
CREATE TABLE `document_views` (
    `id`           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `document_id`  INT UNSIGNED NOT NULL,
    `user_id`      INT UNSIGNED DEFAULT NULL COMMENT 'NULL nếu khách vãng lai',
    `ip_address`   VARCHAR(45) DEFAULT NULL,
    `viewed_at`    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_views_document`
        FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_views_user`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE,
    INDEX `idx_views_document_time` (`document_id`, `viewed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- 10. SHARES - Lịch sử chia sẻ tài liệu
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `shares`;
CREATE TABLE `shares` (
    `id`           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `user_id`      INT UNSIGNED NOT NULL,
    `document_id`  INT UNSIGNED NOT NULL,
    `platform`     VARCHAR(50) NOT NULL COMMENT 'copy_link, facebook, zalo, ...',
    `share_link`   VARCHAR(500) NOT NULL,
    `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_shares_user`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_shares_document`
        FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX `idx_shares_document` (`document_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- 11. STATISTICS_REPORTS - Lịch sử báo cáo đã xuất
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `statistics_reports`;
CREATE TABLE `statistics_reports` (
    `id`             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `admin_id`       INT UNSIGNED NOT NULL,
    `report_type`    ENUM('documents', 'users', 'downloads', 'violations', 'overview') NOT NULL,
    `period_start`   DATE NOT NULL,
    `period_end`     DATE NOT NULL,
    `file_path`      VARCHAR(500) DEFAULT NULL COMMENT 'Đường dẫn file PDF/Excel đã xuất',
    `created_at`     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_stats_admin`
        FOREIGN KEY (`admin_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX `idx_stats_type_period` (`report_type`, `period_start`, `period_end`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;

-- =====================================================================
-- TRIGGER TỰ ĐỘNG CẬP NHẬT DỮ LIỆU DENORMALIZED
-- =====================================================================

DELIMITER //

-- Trigger: Tự động cập nhật avg_rating và total_ratings khi có rating mới
CREATE TRIGGER `trg_ratings_insert`
AFTER INSERT ON `ratings`
FOR EACH ROW
BEGIN
    UPDATE `documents`
    SET `avg_rating` = (
            SELECT ROUND(AVG(`stars`), 1)
            FROM `ratings`
            WHERE `document_id` = NEW.document_id
        ),
        `total_ratings` = (
            SELECT COUNT(*)
            FROM `ratings`
            WHERE `document_id` = NEW.document_id
        )
    WHERE `id` = NEW.document_id;
END//

-- Trigger: Tự động cập nhật avg_rating khi rating bị xóa
CREATE TRIGGER `trg_ratings_delete`
AFTER DELETE ON `ratings`
FOR EACH ROW
BEGIN
    UPDATE `documents`
    SET `avg_rating` = COALESCE((
            SELECT ROUND(AVG(`stars`), 1)
            FROM `ratings`
            WHERE `document_id` = OLD.document_id
        ), 0),
        `total_ratings` = (
            SELECT COUNT(*)
            FROM `ratings`
            WHERE `document_id` = OLD.document_id
        )
    WHERE `id` = OLD.document_id;
END//

-- Trigger: Tự động tăng view_count khi có lượt xem mới
CREATE TRIGGER `trg_document_views_insert`
AFTER INSERT ON `document_views`
FOR EACH ROW
BEGIN
    UPDATE `documents`
    SET `view_count` = `view_count` + 1
    WHERE `id` = NEW.document_id;
END//

-- Trigger: Tự động tăng download_count khi có lượt tải mới
CREATE TRIGGER `trg_downloads_insert`
AFTER INSERT ON `downloads`
FOR EACH ROW
BEGIN
    UPDATE `documents`
    SET `download_count` = `download_count` + 1
    WHERE `id` = NEW.document_id;
END//

DELIMITER ;

-- =====================================================================
-- VIEW HỖ TRỢ THỐNG KÊ
-- =====================================================================

-- Thống kê tổng quan theo tài liệu
CREATE OR REPLACE VIEW `v_document_stats` AS
SELECT
    d.id,
    d.title,
    d.uploader_id,
    d.category_id,
    d.status,
    d.view_count,
    d.download_count,
    d.avg_rating,
    d.total_ratings,
    (SELECT COUNT(*) FROM comments c WHERE c.document_id = d.id AND c.is_deleted = 0) AS comment_count
FROM documents d;

-- Thống kê báo cáo vi phạm theo trạng thái
CREATE OR REPLACE VIEW `v_violation_stats` AS
SELECT
    status,
    target_type,
    COUNT(*) AS total,
    DATE(created_at) AS report_date
FROM violation_reports
GROUP BY status, target_type, DATE(created_at);

-- Thống kê hoạt động người dùng theo ngày (upload/download/view)
CREATE OR REPLACE VIEW `v_daily_activity` AS
SELECT
    activity_date,
    SUM(uploads) AS uploads,
    SUM(downloads) AS downloads,
    SUM(views) AS views
FROM (
    SELECT DATE(created_at) AS activity_date, COUNT(*) AS uploads, 0 AS downloads, 0 AS views
    FROM documents GROUP BY DATE(created_at)
    UNION ALL
    SELECT DATE(downloaded_at), 0, COUNT(*), 0
    FROM downloads GROUP BY DATE(downloaded_at)
    UNION ALL
    SELECT DATE(viewed_at), 0, 0, COUNT(*)
    FROM document_views GROUP BY DATE(viewed_at)
) t
GROUP BY activity_date
ORDER BY activity_date;

-- =====================================================================
-- VIEW BỔ SUNG
-- =====================================================================

-- Top tài liệu được xem nhiều nhất
CREATE OR REPLACE VIEW `v_top_documents` AS
SELECT
    d.id,
    d.title,
    d.subject,
    d.file_type,
    d.view_count,
    d.download_count,
    d.avg_rating,
    d.total_ratings,
    u.full_name AS uploader_name,
    c.name AS category_name
FROM documents d
LEFT JOIN users u ON d.uploader_id = u.id
LEFT JOIN categories c ON d.category_id = c.id
WHERE d.status = 'approved'
ORDER BY d.view_count DESC, d.avg_rating DESC;

-- Hoạt động gần đây của người dùng
CREATE OR REPLACE VIEW `v_user_activity` AS
SELECT
    u.id AS user_id,
    u.full_name,
    u.email,
    (SELECT COUNT(*) FROM documents WHERE uploader_id = u.id) AS total_uploads,
    (SELECT COUNT(*) FROM downloads WHERE user_id = u.id) AS total_downloads,
    (SELECT COUNT(*) FROM document_views WHERE user_id = u.id) AS total_views,
    (SELECT COUNT(*) FROM comments WHERE user_id = u.id AND is_deleted = 0) AS total_comments,
    (SELECT COUNT(*) FROM ratings WHERE user_id = u.id) AS total_ratings
FROM users u;