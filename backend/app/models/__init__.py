from app.models.academic import Assessment, CohortPercentile
from app.models.analytics import AnalyticsFreshness, Recommendation, StudentAnalytics
from app.models.behaviour import (
    Attendance,
    BehaviourRecord,
    TeacherObservation
)
from app.models.learning_path import LearningPathItem, LearningResource
from app.models.notification import Notification, NotificationPreference
from app.models.student import ParentStudent, Student, TeacherAssignment
from app.models.user import User

from app.models.lifecycle import UserLifecycle, StudentLifecycle, RecordChange

from app.models.assignment import ClassAssignment, AssignmentCompletion

from app.models.competency import Competency, CompetencyObservation

