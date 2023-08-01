from django.urls import path,include

from .views import *


urlpatterns = [
    path('api-auth/', include('rest_framework.urls')),

    path('register/', UserRegistrationView.as_view(), name='user-registration'),
    path('verify/',VerifyOTPView.as_view(),name='verify-otp'),
    path('login/', LoginView.as_view(), name='login'),
    # path('logout/', LogoutView.as_view(), name='logout'),


    path('', CourseSearchAPIView.as_view(), name='course_search'),
    path('course/',CourseListAPIView.as_view() , name='course-list'),
    path('course/create/',CourseCreateAPIView.as_view(),name = 'course-create'),
    path('course/<int:pk>/',CourseDetailAPIView.as_view(),name = 'course-create'),
    path('course/<int:pk>/update/',CourseUpdateAPIView.as_view(),name = 'course-update'),
    path('course/<int:pk>/delete/',CourseDeleteAPIView.as_view(),name = 'course-delete'),

    # path('course/content/', CourseContentListAPIView.as_view(),name='course-content-list'),# all course content endpoint

    path('course/<int:course_pk>/add_content/',  CourseContentCreateAPIView.as_view(), name='course-content-create'),
    path('course/<int:course_pk>/content/', CourseContentFilterAPIView.as_view(), name='course-content-filter'), # content based on the course id
    path('course/<int:course_pk>/content/<int:pk>/', CourseContentDetailAPIView.as_view(), name='course-content-detail'),
    path('course/<int:course_pk>/content/<int:pk>/update/', CourseContentUpdateAPIView.as_view(), name='course-content-update'),
    path('course/<int:course_pk>/content/<int:pk>/delete/', CourseContentDeleteAPIView.as_view(), name='course-content-delete'),

    # student course purchase

    path('student_courses/', StudentCoursesAPI.as_view(), name='student_courses'),
    path('course/<int:course_id>/purchase/',CoursePaymentView.as_view(), name='initiate-payment'),
    path('payment/success/', execute_payment, name='payment_success'),

]