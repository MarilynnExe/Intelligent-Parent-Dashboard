USE school_dashboard_db;
DESCRIBE STUDENTS;
DESCRIBE ASSESSMENTS;
DESCRIBE ATTENDANCE;
DESCRIBE TEACHER_ASSIGNMENTS;
DESCRIBE STUDENT_ANALYTICS;

SHOW CREATE TABLE PARENT_STUDENT;
SHOW CREATE TABLE TEACHER_ASSIGNMENTS;
SHOW CREATE TABLE ASSESSMENTS;
SHOW CREATE TABLE ATTENDANCE;

SELECT a.*
FROM ASSESSMENTS a
LEFT JOIN STUDENTS s
ON a.student_id = s.student_id
WHERE s.student_id IS NULL;

SELECT att.* 
FROM attendance att 
LEFT JOIN students s ON att.student_id = s.student_id 
WHERE s.student_id IS NULL;

SELECT b.* 
FROM behaviour_records b 
LEFT JOIN students s ON b.student_id = s.student_id 
WHERE s.student_id IS NULL;

SELECT o.* 
FROM teacher_observations o 
LEFT JOIN students s ON o.student_id = s.student_id 
WHERE s.student_id IS NULL;

SELECT an.* 
FROM student_analytics an 
LEFT JOIN students s ON an.student_id = s.student_id 
WHERE s.student_id IS NULL;
