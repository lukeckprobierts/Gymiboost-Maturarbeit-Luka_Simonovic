from extensions import db
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    chat_sessions = db.relationship('ChatSession', backref='user', lazy=True)
    
    # Add subscription fields
    has_subscription = db.Column(db.Boolean, default=False)
    subscription_end = db.Column(db.DateTime)

    # Free trial tracking fields
    free_trial_start = db.Column(db.DateTime)
    chat_message_count = db.Column(db.Integer, default=0)
    exam_sim_count = db.Column(db.Integer, default=0)
    task_gen_count = db.Column(db.Integer, default=0)
    last_reset = db.Column(db.DateTime)

    @property
    def has_active_subscription(self):
        if not self.has_subscription:
            return False
        if not self.subscription_end:
            return False
        return self.subscription_end > datetime.utcnow()

    @property
    def on_free_trial(self):
        return not self.has_active_subscription  # Allows free trial if not subscribed

    def reset_free_trial_limits(self):
        self.chat_message_count = 0
        self.exam_sim_count = 0
        self.task_gen_count = 0
        self.last_reset = datetime.utcnow()
        db.session.commit()

    def check_trial_limits(self, category):
        from datetime import datetime as _dt, timedelta
        now = _dt.utcnow()
        if not self.last_reset or (now - self.last_reset) > timedelta(weeks=1):
            self.reset_free_trial_limits()
        limits = {'chat': 10, 'exam': 2, 'task': 5}
        count_map = {
            'chat': self.chat_message_count,
            'exam': self.exam_sim_count,
            'task': self.task_gen_count
        }
        return count_map[category] < limits[category]

    def increment_trial_count(self, category):
        from datetime import datetime as _dt, timedelta
        now = _dt.utcnow()
        if not self.last_reset or (now - self.last_reset) > timedelta(weeks=1):
            self.reset_free_trial_limits()
        if category == 'chat':
            self.chat_message_count += 1
        elif category == 'exam':
            self.exam_sim_count += 1
        elif category == 'task':
            self.task_gen_count += 1
        db.session.commit()

    def check_subscription_status(self):
        """
        Updates subscription status based on end date
        """
        if not self.subscription_end:
            self.has_subscription = False
            return
            
        if self.subscription_end < datetime.utcnow():
            self.has_subscription = False
            self.subscription_end = None
            db.session.commit()

class ChatSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, default="New Chat")
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    messages = db.relationship('Message', backref='session', lazy=True, cascade="all, delete-orphan")
    context_query_count = db.Column(db.Integer, default=0)
    rag_context = db.Column(db.Text, default="")


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'), nullable=False)
    is_user = db.Column(db.Boolean, default=True)  # True if user message, False if bot response.
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class SavedTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    topic = db.Column(db.String(150), nullable=False, default='')
    tasksheet = db.Column(db.Text, nullable=False)
    solutionsheet = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='saved_tasks')


class UserTopicMastery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    subject = db.Column(db.String(64), nullable=False, index=True)  # 'Deutsch' or 'Mathematik'
    topic = db.Column(db.String(150), nullable=False)
    mastery = db.Column(db.Integer, nullable=False, default=0)  # 0..100
    signals_count = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'subject', 'topic', name='uq_user_subject_topic'),
    )


class ExamAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    subject = db.Column(db.String(64), nullable=False, index=True)  # 'Deutsch' or 'Mathematik'
    exam_filename = db.Column(db.String(255), nullable=True)
    grade = db.Column(db.Float, nullable=True)  # 1..6 (optional if not parsed)
    feedback = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='exam_attempts')


class ChatAnalysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'), nullable=False, index=True)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False, index=True)
    subject = db.Column(db.String(64), nullable=False)
    topics_json = db.Column(db.Text, nullable=False, default='[]')  # JSON array of topic names
    relevance_score = db.Column(db.Float, nullable=False, default=0.0)  # 0..1
    learning_signal = db.Column(db.String(16), nullable=False, default='neutral')  # positive/neutral/negative
    delta_json = db.Column(db.Text, nullable=False, default='{}')  # JSON map { topic: delta_points }
    summary = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='chat_analyses')
    session = db.relationship('ChatSession', backref=db.backref('analyses', cascade="all, delete-orphan"))
    message = db.relationship('Message', backref=db.backref('analysis_entry', cascade="all, delete-orphan", uselist=False))


class CoursePlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    subject = db.Column(db.String(64), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    plan_json = db.Column(db.Text, nullable=False, default='{}')  # future: syllabus, modules, checkpoints
    status = db.Column(db.String(32), nullable=False, default='draft')  # draft/active/completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='course_plans')


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(64), nullable=False, index=True)
    level = db.Column(db.String(32), nullable=False, default='Mittelstufe')
    summary = db.Column(db.Text, nullable=True)
    goals = db.Column(db.Text, nullable=True)
    language = db.Column(db.String(32), nullable=False, default='Deutsch')
    audience = db.Column(db.String(64), nullable=True, default='Gemischt')
    estimated_minutes = db.Column(db.Integer, nullable=False, default=120)
    modules_count = db.Column(db.Integer, nullable=False, default=6)
    tags_json = db.Column(db.Text, nullable=False, default='[]')  # JSON array of strings
    rating_avg = db.Column(db.Float, nullable=False, default=0.0)
    ratings_count = db.Column(db.Integer, nullable=False, default=0)
    learners_count = db.Column(db.Integer, nullable=False, default=0)
    is_public = db.Column(db.Boolean, nullable=False, default=True)
    license = db.Column(db.String(64), nullable=True, default='CC BY-SA')
    allow_clone = db.Column(db.Boolean, nullable=False, default=True)
    cover_prompt = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', backref='created_courses')
    modules = db.relationship('CourseModule', backref='course', lazy=True, cascade="all, delete-orphan", order_by="CourseModule.index")


class CourseModule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    index = db.Column(db.Integer, nullable=False, default=0)  # 0-based order
    title = db.Column(db.String(200), nullable=False)
    minutes_estimate = db.Column(db.Integer, nullable=False, default=20)
    content_html = db.Column(db.Text, nullable=False, default='')  # rich HTML including interactive blocks
    extras_json = db.Column(db.Text, nullable=False, default='{}')  # JSON for quizzes, metadata, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assets = db.relationship('CourseAsset', backref='module', lazy=True, cascade="all, delete-orphan")


class CourseAsset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    module_id = db.Column(db.Integer, db.ForeignKey('course_module.id'), nullable=True, index=True)
    kind = db.Column(db.String(32), nullable=False, default='html')  # html/svg/audio/json
    mime_type = db.Column(db.String(64), nullable=True)
    title = db.Column(db.String(200), nullable=True)
    content_text = db.Column(db.Text, nullable=True)          # for inline html/svg/json
    file_path = db.Column(db.String(255), nullable=True)      # server path if file-based (e.g., audio)
    file_url = db.Column(db.String(255), nullable=True)       # public URL if served via static
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CourseEnrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default='active')  # active/completed
    progress_percent = db.Column(db.Integer, nullable=False, default=0)  # 0..100
    checkpoints_json = db.Column(db.Text, nullable=False, default='{}')  # JSON map for module progress
    last_accessed = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='enrollments')
    course = db.relationship('Course', backref='enrollments')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'course_id', name='uq_user_course_enrollment'),
    )


class CourseRating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    stars = db.Column(db.Integer, nullable=False, default=5)  # 1..5
    review = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='course_ratings')
    course = db.relationship('Course', backref='ratings')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'course_id', name='uq_user_course_rating'),
    )


class CourseSave(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='saved_courses')
    course = db.relationship('Course', backref='saves')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'course_id', name='uq_user_course_save'),
    )


class CourseProgressEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    module_id = db.Column(db.Integer, db.ForeignKey('course_module.id'), nullable=True, index=True)
    event_type = db.Column(db.String(64), nullable=False)  # e.g., 'module_start','module_complete','quiz_answer','checkpoint'
    payload_json = db.Column(db.Text, nullable=False, default='{}')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='course_progress_events')
    course = db.relationship('Course', backref='progress_events')
    module = db.relationship('CourseModule', backref='progress_events')


class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    module_id = db.Column(db.Integer, db.ForeignKey('course_module.id'), nullable=False, index=True)
    slug = db.Column(db.String(64), nullable=False)  # stable reference from agent/html
    title = db.Column(db.String(200), nullable=True)
    data_json = db.Column(db.Text, nullable=False, default='{}')  # {questions:[{type,question,choices,answer_index,explanation,...}], meta:{}}
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    module = db.relationship('CourseModule', backref='quizzes')

    __table_args__ = (
        db.UniqueConstraint('module_id', 'slug', name='uq_quiz_module_slug'),
    )


class QuizAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False, index=True)
    answers_json = db.Column(db.Text, nullable=False, default='[]')  # array of answers/submissions
    correct_count = db.Column(db.Integer, nullable=False, default=0)
    total_count = db.Column(db.Integer, nullable=False, default=0)
    score = db.Column(db.Float, nullable=False, default=0.0)  # 0..1
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='quiz_attempts')
    quiz = db.relationship('Quiz', backref='attempts')


class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    module_id = db.Column(db.Integer, db.ForeignKey('course_module.id'), nullable=False, index=True)
    slug = db.Column(db.String(64), nullable=False)
    question = db.Column(db.String(255), nullable=False)
    options_json = db.Column(db.Text, nullable=False, default='[]')  # ["A","B","C",...]
    multiple = db.Column(db.Boolean, nullable=False, default=False)
    is_open = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    module = db.relationship('CourseModule', backref='polls')

    __table_args__ = (
        db.UniqueConstraint('module_id', 'slug', name='uq_poll_module_slug'),
    )


class PollVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    options_json = db.Column(db.Text, nullable=False, default='[]')  # indices or option strings
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    poll = db.relationship('Poll', backref='votes')
    user = db.relationship('User', backref='poll_votes')

    __table_args__ = (
        db.UniqueConstraint('poll_id', 'user_id', name='uq_poll_user_vote'),
    )


class FlashcardDeck(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    module_id = db.Column(db.Integer, db.ForeignKey('course_module.id'), nullable=False, index=True)
    slug = db.Column(db.String(64), nullable=False)
    title = db.Column(db.String(200), nullable=True)
    config_json = db.Column(db.Text, nullable=False, default='{}')  # e.g., {strategy:"sm2-lite"}
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    module = db.relationship('CourseModule', backref='flashcard_decks')

    __table_args__ = (
        db.UniqueConstraint('module_id', 'slug', name='uq_deck_module_slug'),
    )


class Flashcard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deck_id = db.Column(db.Integer, db.ForeignKey('flashcard_deck.id'), nullable=False, index=True)
    front_text = db.Column(db.Text, nullable=False)
    back_text = db.Column(db.Text, nullable=False)
    extra_json = db.Column(db.Text, nullable=False, default='{}')  # tags, hints, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    deck = db.relationship('FlashcardDeck', backref='cards')


class FlashcardReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    card_id = db.Column(db.Integer, db.ForeignKey('flashcard.id'), nullable=False, index=True)
    ease = db.Column(db.Integer, nullable=False, default=3)  # 1..5 (again, hard, good, easy etc.)
    interval_days = db.Column(db.Integer, nullable=False, default=0)
    due_at = db.Column(db.DateTime, nullable=True)
    last_review_at = db.Column(db.DateTime, default=datetime.utcnow)
    reps = db.Column(db.Integer, nullable=False, default=0)
    lapses = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='flashcard_reviews')
    card = db.relationship('Flashcard', backref='reviews')


class ModuleNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    module_id = db.Column(db.Integer, db.ForeignKey('course_module.id'), nullable=False, index=True)
    content_text = db.Column(db.Text, nullable=False, default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='module_notes')
    course = db.relationship('Course', backref='module_notes')
    module = db.relationship('CourseModule', backref='notes')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'module_id', name='uq_note_user_module'),
    )


class ModuleChecklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    module_id = db.Column(db.Integer, db.ForeignKey('course_module.id'), nullable=False, index=True)
    items_json = db.Column(db.Text, nullable=False, default='[]')  # [{label, done}]
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='module_checklists')
    course = db.relationship('Course', backref='module_checklists')
    module = db.relationship('CourseModule', backref='checklists')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'module_id', name='uq_checklist_user_module'),
    )


class ProgressAISummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    subject = db.Column(db.String(64), nullable=False, index=True)  # 'Deutsch' or 'Mathematik'
    strengths_json = db.Column(db.Text, nullable=False, default='[]')  # string[]
    weaknesses_json = db.Column(db.Text, nullable=False, default='[]')  # string[]
    tips_json = db.Column(db.Text, nullable=False, default='[]')  # string[]
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='progress_ai_summaries')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'subject', name='uq_user_subject_ai_summary'),
    )
