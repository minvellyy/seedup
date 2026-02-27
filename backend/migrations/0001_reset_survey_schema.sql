-- SQLite Migration SQL for resetting the survey schema

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- Drop existing tables if they exist
DROP TABLE IF EXISTS survey_answers;
DROP TABLE IF EXISTS survey_questions;
DROP TABLE IF EXISTS users;

-- Create users table
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    username TEXT NOT NULL,
    name TEXT,
    phone TEXT,
    birth_date TEXT,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create survey_questions table
CREATE TABLE survey_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    text TEXT NOT NULL,
    answer_type TEXT NOT NULL,
    options_json TEXT,
    order_no INTEGER NOT NULL,
    parent_question_id INTEGER REFERENCES survey_questions(id) ON DELETE CASCADE,
    show_if_question_id INTEGER REFERENCES survey_questions(id) ON DELETE CASCADE,
    show_if_value TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create survey_answers table
CREATE TABLE survey_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    question_id INTEGER REFERENCES survey_questions(id) ON DELETE CASCADE,
    value_text TEXT,
    value_number REAL,
    value_choice TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(user_id, question_id)
);
