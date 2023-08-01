import re
from .models import *
from rest_framework import serializers
from django.contrib.auth import authenticate


class OTPVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

    class Meta:
        model = User
        field = ['email','otp']

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    username = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ('username','name', 'email', 'is_student', 'is_teacher', 'password', 'confirm_password')

    def validate(self, data):
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        if password != confirm_password:
            raise serializers.ValidationError("Passwords do not match.")

        if not re.search(r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$', password):
            raise serializers.ValidationError("Password must be at least 8 characters long and contain at least one uppercase letter, one digit, and one special character.")

        email = data.get('email')
        username = email if email else data.get('username')
        data['username'] = username

        return data

    def validate_name(self, value):
        if not value.replace(" ", "").isalpha():
            raise serializers.ValidationError("Name can only contain letters and spaces and should not have digits or symbols.")
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        email = validated_data.get('email')
        username = email if email else validated_data.get('username')

        user = User.objects.create(username=username, **validated_data)
        user.set_password(password)
        user.save()
        return user

class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ('user', 'email', 'name')

class TeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Teacher
        fields = ('user', 'email', 'name')

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(style={'input_type': 'password'})

    def validate(self, data):
        username = data.get('username')
        password = data.get('password')

        if username and password:
            user = authenticate(username=username, password=password)
            if not user:
                raise serializers.ValidationError('Invalid username or password.')
        else:
            raise serializers.ValidationError('Must include "username" and "password".')

        data['user'] = user
        return data
    
    class Meta:
        model = User
        fields = ['username','password']

class CourseSerializer(serializers.ModelSerializer):
    Instructor = serializers.SerializerMethodField()
    student_names = serializers.SerializerMethodField()

    class Meta:
        model = Course
        exclude = ['post_date']

    def get_Instructor(self, course):
        # Access the related Teacher object and return the name
        return course.Instructor.name
    
    def get_student_names(self, course):
        # Fetch the names of students who purchased this course
        teacher = self.context['request'].user.teacher
        students = Student.objects.filter(payment__course=course, payment__teacher=teacher)
        return [student.name for student in students]
    
class CourseDetailSerializer(serializers.ModelSerializer):
    Instructor = serializers.SerializerMethodField()

    class Meta:
        model = Course
        exclude = ['post_date']

    def get_Instructor(self, course):
        # Access the related Teacher object and return the name
        return course.Instructor.name   

class CourseContentSerializer(serializers.ModelSerializer):
    Instructor = serializers.SerializerMethodField()

    class Meta:
        model = CourseContent
        fields = '__all__'
        read_only_fields = ['course']

    def get_Instructor(self, content):
        return content.course.Instructor.name
 
class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        exclude = ['course', 'teacher','student']
        read_only_fields = ['course', 'teacher', 'price','purchased_at']

    def create(self, validated_data):
        # Set the student field to request.user.student by default
        validated_data['student'] = self.context['request'].user.student
        return super().create(validated_data)
    
