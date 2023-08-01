import random
import smtplib
import socket
import paypalrestsdk 

from .models import *
from .serializers import *

from rest_framework.views import APIView
from rest_framework import status,generics
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import PermissionDenied,APIException

from django.conf import settings
from django.core.mail import send_mail
from django.core.exceptions import ValidationError

class UserRegistrationView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer


    def create(self, request, *args, **kwargs):
        data = request.data
        user_type = None
        if data.get('is_student') and data.get('is_teacher'):
            return Response({"error": "User cannot be both student and teacher."}, status=status.HTTP_400_BAD_REQUEST)
        elif data.get('is_student'):
            user_type = 'student'
        elif data.get('is_teacher'):
            user_type = 'teacher'
            
        email = data.get('email')
        if User.objects.filter(email=email).exists():
            return Response({"error": "Email is already registered. Please log in instead."}, status=status.HTTP_409_CONFLICT)
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        # Generate and send OTP via email
        otp = str(random.randint(1000, 9999))

        try:
            send_mail(
                'OTP Verification',
                f'Your OTP for registration is: {otp}',
                settings.EMAIL_HOST_USER,
                [data.get('email')],
                fail_silently=False,
            )
            request.session['otp'] = otp
            request.session['registration_data'] = data
            request.session['is_teacher'] = user_type == 'teacher'
            request.session['is_student'] = user_type == 'student'

            return Response({"detail": "OTP has been sent to your email. Please verify."}, status=status.HTTP_200_OK)

        except (smtplib.SMTPConnectError, socket.gaierror):
            # Handle the email sending error
            return Response({"error": "Failed to send OTP. Please try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VerifyOTPView(APIView):
    serializer_class = OTPVerificationSerializer

    def post(self, request):
        registration_data = request.session.get('registration_data')
        if not registration_data:
            return Response({"error": "Registration data not found. Please try registering again."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = OTPVerificationSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        userotp = serializer.validated_data.get('otp')
        email = serializer.validated_data.get('email')

        is_teacher = request.session.get('is_teacher')
        is_student = request.session.get('is_student')
        stored_otp = request.session.get('otp')

        if userotp and email and (is_teacher or is_student):
            if userotp == stored_otp:
                try:
                    existing_user = User.objects.get(email=email)
                    return Response({"error": "Email is already registered. Please log in instead."}, status=status.HTTP_409_CONFLICT)
                except User.DoesNotExist:
                    # Create the user and associated model objects
                    username = email
                    user = User.objects.create_user(
                        username=username,
                        password=registration_data.get('password'),
                        email=email,
                        name=registration_data.get('name'),
                    )
                    if is_teacher:
                        teacher = Teacher.objects.create(
                            user=user,
                            email=email,
                            name=registration_data.get('name'),
                        )
                        if teacher:
                            user.is_teacher = True
                            user.save()
                            teacher.save()
                    elif is_student:
                        student = Student.objects.create(
                            user=user,
                            email=email,
                            name=registration_data.get('name'),
                        )
                        if student:
                            user.is_student = True
                            user.save()
                            student.save()

                    # Clear the session data
                    request.session.pop('otp', None)
                    request.session.pop('registration_data', None)
                    request.session.pop('is_teacher', None)
                    request.session.pop('is_student', None)

                    return Response({"detail": "User saved successfully."}, status=status.HTTP_201_CREATED)

            else:
                return Response({"error": "Invalid OTP. Please try again."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"error": "OTP verification failed."}, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    serializer_class = LoginSerializer

    def post(self, request):
        # import pdb;pdb.set_trace()
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        data = {
            'access': str(refresh.access_token),
        }

        if user.is_teacher:
            data['message'] = "Login successful. Redirecting to teacher dashboard."
        elif user.is_student:
            data['message'] = "Login successful. Redirecting to student dashboard."
        else:
            data['message'] = "Login successful."

        # Return the response with the token data and status code 200 (OK)
        return Response(data, status=status.HTTP_200_OK)

class CourseSearchAPIView( generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseDetailSerializer
    filter_backends = [SearchFilter]
    search_fields = ['title', 'description', 'Instructor__name']

    def get_queryset(self):
        user = self.request.user

        if user.is_student:
            queryset = Course.objects.all()
        elif user.is_teacher:
            queryset = Course.objects.filter(Instructor=user.teacher)
        else:
            queryset = Course.objects.none()

        query_param = self.request.query_params.get('q', None)
        if query_param:
            queryset = queryset.filter(title__icontains=query_param)

        return queryset   
    
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            if not isinstance(queryset, dict):
                serializer = self.get_serializer(queryset, many=True)
                return Response({"data": serializer.data})
            return Response({"data": {}})
        except APIException as e:
            return Response({"message": "Something went wrong. Please try again later."}, status=e.status_code)
        except Exception as e:
            return Response({"message": "Something went wrong. Please contact support."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CourseListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseSerializer

    def get_queryset(self):
        user = self.request.user

        if user.is_student:
            raise PermissionDenied(detail="Students are not allowed here.")

        if user.is_teacher:
            return Course.objects.filter(Instructor=user.teacher)

        return Course.objects.none()
    
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            if not isinstance(queryset, dict):
                serializer = self.get_serializer(queryset, many=True)
                return Response({"data": serializer.data})
            return Response({"data": {}})
        except PermissionDenied as e:
            return Response({"message": str(e)}, status=status.HTTP_403_FORBIDDEN) 
        except APIException as e:
            return Response({"message": "Something went wrong. Please try again later."}, status=e.status_code)
        except Exception as e:
            return Response({"message": "Something went wrong. Please contact support."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CourseCreateAPIView(generics.CreateAPIView):
    serializer_class = CourseDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Course.objects.none()

    def perform_create(self, serializer):
        user = self.request.user

        if user.is_student:
            raise PermissionDenied(detail="Students cannot create courses. They can only learn.")

        if user.is_teacher:
            try:
                teacher = Teacher.objects.get(user=user)
            except Teacher.DoesNotExist:
                raise serializers.ValidationError("Teacher profile not found. Please create a teacher profile.")

        serializer.save(Instructor=teacher)

        # Send email notification to students who purchased the author's other courses
        students = Student.objects.filter(payment__teacher=teacher)
        for student in students:
            send_mail(
                'New Course by Author',
                f'A new course has been designed by the author of one of your purchased courses.',
                'sender@example.com',  # Replace with your sender email address
                [student.user.email],
                fail_silently=True,
            )

    def create(self, request, *args, **kwargs):
        try:
            response = super().create(request, *args, **kwargs)
            serializer_data = response.data
            return Response({"message": "new course created successfully",
                "data": serializer_data}, status=201)
        except PermissionDenied as e:
            return Response({"message": str(e)}, status=status.HTTP_403_FORBIDDEN) 
        except APIException as e:
            return Response({"message": "Something went wrong. Please try again later."}, status=e.status_code)
        except Exception as e:
            return Response({"message": "Something went wrong. Please contact support."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CourseDetailAPIView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Course.objects.all()

        if user.is_student:
            raise PermissionDenied(detail="Students are not alllowed here")
        elif user.is_teacher:
            return queryset.filter(Instructor__user=user)
        else:
            return Course.objects.none()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        user = self.request.user

        if user.is_student:
            return super().retrieve(request, *args, **kwargs)

        if user.is_teacher and user.teacher == instance.Instructor:
            return super().retrieve(request, *args, **kwargs)
        else:
            raise PermissionDenied(detail="You are not allowed to view this course detail.")
        
    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response({"data": serializer.data})
        except PermissionDenied as e:
            return Response({"message": str(e)}, status=status.HTTP_403_FORBIDDEN) 
        
class CourseUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseDetailSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        user = self.request.user
        queryset = Course.objects.filter(Instructor__user=user)
        return queryset

    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            user = self.request.user

            if user.is_student:
                raise PermissionDenied("Students are not allowed to update courses.")
            if not user.is_teacher:
                raise PermissionDenied("Only teachers can update course content.")

            # Ensure the teacher is the instructor of the course
            if instance.Instructor.user != user:
                raise PermissionDenied("You are not allowed to update course content for this course.")

            response = super().update(request, *args, **kwargs)
            serializer_data = response.data
            return Response({"message": "Course updated successfully","data" : serializer_data}, status=200)
        except PermissionDenied as e:
            return Response({"message": str(e)}, status=status.HTTP_403_FORBIDDEN) 

class CourseDeleteAPIView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseDetailSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        user = self.request.user
        queryset = Course.objects.filter(Instructor__user=user)
        return queryset

    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        try:
            instance= self.get_object()
            user = self.request.user

            if user.is_student:
                raise PermissionDenied("Students are not allowed to delete courses.")
            
            if user != instance.Instructor.user:
                raise PermissionDenied("You are not allowed to delete this course.")

            response = super().destroy(request, *args, **kwargs)
            return Response({"message": "Course deleted successfully"}, status=200)
        except PermissionDenied as e:
            return Response({"message": str(e)}, status=status.HTTP_403_FORBIDDEN) 
        # except APIException as e:
        #     return Response({"message": "Something went wrong. Please try again later."}, status=e.status_code)
        # except Exception as e:
        #     return Response({"message": "Something went wrong. Please contact support."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
   
class CourseContentCreateAPIView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseContentSerializer

    def perform_create(self, serializer):
        if self.request.user.is_student:
            raise PermissionDenied("Students are not allowed to create course content.")

        course_id = self.kwargs['course_pk']
        try:
            course = Course.objects.get(pk=course_id)
        except Course.DoesNotExist:
            raise serializers.ValidationError("Course not found.")
            
        if self.request.user != course.Instructor.user:
            raise PermissionDenied("You can only create content for your own courses.")
        
        serializer.save(course=course)

        students = Student.objects.filter(payment__course=course)
        for student in students:
            send_mail(
                'New Course Content Added',
                f'A new topic has been added to the course: {course.title}',
                'sender@example.com',  # Replace with your sender email address
                [student.user.email],
                fail_silently=True,
            )

    def create(self, request, *args, **kwargs):
        try:
            response = super().create(request, *args, **kwargs)
            serializer_data = response.data
            return Response({"message": "New course content created successfully","data" : serializer_data}, status=201)
        except PermissionDenied as e:
            return Response({"message": str(e)}, status=status.HTTP_403_FORBIDDEN) 
        except APIException as e:
            return Response({"message": "Something went wrong. Please try again later."}, status=e.status_code)
        except Exception as e:
            return Response({"message": "Something went wrong. Please contact support."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CourseContentFilterAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseContentSerializer

    def get_queryset(self):
        course_pk = self.kwargs['course_pk']
        user = self.request.user

        try:
            course = Course.objects.get(pk=course_pk)
        except Course.DoesNotExist:
            raise serializers.ValidationError("Course not found.")
        
        if user.is_student or (user.is_teacher and user.teacher == course.Instructor):
            queryset = CourseContent.objects.filter(course_id=course_pk)
            if not queryset.exists():
                raise serializers.ValidationError("No content available for this course.")
            return queryset

        raise PermissionDenied("You are not allowed to view course content, Since this is not your course")

    
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            if not isinstance(queryset, dict):
                serializer = self.get_serializer(queryset, many=True)
                return Response({"data": serializer.data})
            return Response({
                'message': 'Contents that are created for this particular course',
                'data': {
                }
            })
        except PermissionDenied as e:
            return Response({"message": str(e)}, status=status.HTTP_403_FORBIDDEN) 
        
        # except APIException as e:
        #     return Response({"message": "Something went wrong. Please try again later."}, status=e.status_code)
        # except Exception as e:
        #     return Response({"message": "Something went wrong. Please contact support."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
class CourseContentDetailAPIView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    queryset = CourseContent.objects.all()
    serializer_class = CourseContentSerializer

    def get_queryset(self):
        course_pk = self.kwargs.get('course_pk')
        return self.queryset.filter(course__pk=course_pk)
    
    def get_object(self):
        obj = super().get_object()
        user = self.request.user

        course = obj.course
        if user.is_teacher and user.teacher != course.Instructor:
            raise PermissionDenied("This is not your course, so you are not allowed to view content details.")

        return 
       
class CourseContentUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    queryset = CourseContent.objects.all()
    serializer_class = CourseContentSerializer

    def get_queryset(self):
        course_pk = self.kwargs.get('course_pk')
        return self.queryset.filter(course__pk=course_pk)
    
    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self.check_and_update(request, *args, **kwargs)

    def check_and_update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            user = self.request.user

            if user.is_student:
                raise PermissionDenied("Students are not allowed to update course content.")

            # Ensure user is a teacher
            if not user.is_teacher:
                raise PermissionDenied("Only teachers can update course content.")

            # Ensure the teacher is the instructor of the course
            if instance.course.Instructor.user != user:
                raise PermissionDenied("You are not allowed to update course content for this course.")

            response = self.update(request, *args, **kwargs)
            serializer_data = response.data
            return Response({"message": "Course content updated successfully", "data": serializer_data}, status=200)
        except PermissionDenied as e:
            return Response({"message": str(e)}, status=status.HTTP_403_FORBIDDEN)

class CourseContentDeleteAPIView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseContentSerializer

    def get_queryset(self):
        course_pk = self.kwargs.get('course_pk')
        return CourseContent.objects.filter(course__pk=course_pk)

    def delete(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            user = self.request.user

            if user.is_student:
                raise PermissionDenied("You are not allowed to delete course content.")

            if user.is_teacher:
                teacher = Teacher.objects.get(user=user)
                if teacher != instance.course.Instructor:
                    raise PermissionDenied("You are not allowed to delete course content for this course.")
                

            response =  self.destroy(request, *args, **kwargs)
            return Response({"message": "Course content deleted successfully"}, status=200)
        except PermissionDenied as e:
            return Response({"message": str(e)}, status=status.HTTP_403_FORBIDDEN) 
        # except APIException as e:
        #     return Response({"message": "Something went wrong. Please try again later."}, status=e.status_code)
        # except Exception as e:
        #     return Response({"message": "Something went wrong. Please contact support."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StudentCoursesAPI(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, *args, **kwargs):
        try:
            if request.user.is_teacher:
                raise PermissionDenied(detail="Teachers are not allowed to access student courses.")

            student_instance = request.user.student

            courses = Course.objects.filter(purchases_courses__student=student_instance)

            course_data = []
            for course in courses:
                # serializer = CourseDetailSerializer(course)
                contents = CourseContent.objects.filter(course=course)
                content_serializer = CourseContentSerializer(contents, many=True)
                course_data.append({
                    'course_id': course.id,
                    'course_name': course.title,
                    'contents': content_serializer.data
                })

            return Response({
                'status': status.HTTP_200_OK,
                'message': 'Courses purchased by the student.',
                'data': {
                    'courses': course_data
                }
            })
        except PermissionDenied as e:
            return Response({"message": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except APIException as e:
            return Response({"message": "Something went wrong. Please try again later."}, status=e.status_code)
        except Exception as e:
            return Response({"message": "Something went wrong. Please contact support."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CoursePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, course_id):
        try:
            course = Course.objects.get(pk=course_id)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        if request.user.is_teacher:
            return Response({'message': 'Teachers are not allowed to purchase courses.'}, status=status.HTTP_403_FORBIDDEN)

        if Payment.objects.filter(student=request.user.student, course=course).exists():
            return Response({'message': 'You have already purchased this course.'}, status=status.HTTP_200_OK)

        try:
            paypalrestsdk.configure({
                'mode': 'sandbox' if settings.PAYPAL_SANDBOX_MODE else 'live',
                'client_id': settings.PAYPAL_CLIENT_ID,
                'client_secret': settings.PAYPAL_SECRET_KEY
            })

            payment = paypalrestsdk.Payment({
                "intent": "sale",
                "payer": {
                    "payment_method": "paypal",
                },
                "redirect_urls": {
                    "return_url": "http://localhost:8000/payment/success/",
                    "cancel_url": "http://localhost:8000/payment/cancel/"
                },
                "transactions": [{
                    "amount": {
                        "total": str(course.price),
                        "currency": "USD"
                    },
                    "description": f"Payment for {course.id}"
                }]
            })

            if payment.create():
                # Extract the approval URL from the payment response
                for link in payment.links:
                    if link['rel'] == 'approval_url':
                        approval_url = link['href']
                        break
                else:
                    return Response({'error': 'Unable to retrieve approval URL.'}, status=status.HTTP_400_BAD_REQUEST)

                # Save the Payment data in the model without the transaction_id for now
                payment_obj = Payment.objects.create(
                    student=request.user.student,
                    teacher=course.Instructor,
                    course=course,
                )

                serializer = PaymentSerializer(payment_obj)
                return Response({'approval_url': approval_url, 'payment_data': serializer.data}, status=status.HTTP_201_CREATED)

            return Response({'error': 'Unable to initiate payment.'}, status=status.HTTP_400_BAD_REQUEST)

        except ConnectionError:
            return Response({'error': 'Connection error. Please try again later.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        except Exception as e:
            return Response({'error': 'Something went wrong. Please contact support.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def execute_payment(request):
    payment_id = request.query_params.get('paymentId')
    payer_id = request.query_params.get('PayerID')

    try:
        payment = paypalrestsdk.Payment.find(payment_id)
    except paypalrestsdk.exceptions.ResourceNotFound:
        return Response({'error': 'Payment not found.'}, status=status.HTTP_404_NOT_FOUND)

    if payment.execute({"payer_id": payer_id}):
        course_id = payment.transactions[0].description.split('Payment for ')[1]
        try:
            payment_objs = Payment.objects.filter(course_id=course_id)

            for payment_obj in payment_objs:
                payment_obj.transaction_id = payment.id
                payment_obj.purchased_at = timezone.now()
                payment_obj.save()

            return Response({'message': 'Payment completed successfully.'}, status=status.HTTP_200_OK)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment object not found.'}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response({'error': 'Unable to complete payment.'}, status=status.HTTP_400_BAD_REQUEST)

