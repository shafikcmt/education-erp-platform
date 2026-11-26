"""Timetable routes (Phase 7 M7). Tenant host only."""

from django.urls import path

from apps.timetable.api import views as v

app_name = "timetable"

urlpatterns = [
    path("timetable/schedules/", v.SchedulesView.as_view(), name="schedules"),
    path(
        "timetable/schedules/<str:schedule_id>/periods/",
        v.SchedulePeriodsView.as_view(),
        name="schedule-periods",
    ),
    path("timetable/rooms/", v.RoomsView.as_view(), name="rooms"),
    path("timetable/slots/", v.SlotsView.as_view(), name="slots"),
    path("timetable/slots/<str:slot_id>/", v.SlotDetailView.as_view(), name="slot"),
    path("timetable/my/", v.MyTimetableView.as_view(), name="my"),
]
