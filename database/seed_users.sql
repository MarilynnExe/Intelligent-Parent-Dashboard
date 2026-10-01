USE school_dashboard_db;

TRUNCATE TABLE users;

INSERT INTO users
(
    full_name,
    email_or_username,
    password_hash,
    role,
    phone_number
)
VALUES
(
    'System Administrator',
    'admin',
    '$2b$12$JVb.qWWvORyYROv8UhsKLeGes.gwkhOPDemS5zjW08V9crGjCe.Sm',
    'ADMIN',
    '0700000001'
),
(
    'Test Teacher',
    'teacher',
    '$2b$12$JVb.qWWvORyYROv8UhsKLeGes.gwkhOPDemS5zjW08V9crGjCe.Sm',
    'TEACHER',
    '0700000002'
),
(
    'Test Parent',
    'parent',
    '$2b$12$JVb.qWWvORyYROv8UhsKLeGes.gwkhOPDemS5zjW08V9crGjCe.Sm',
    'PARENT',
    '0700000003'
);