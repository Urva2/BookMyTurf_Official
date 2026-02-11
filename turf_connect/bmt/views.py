from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import StudentSignUpForm, TeacherSignUpForm

# Registration
def register_player(request):
    if request.method == 'POST':
        form = StudentSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('player_home')
    else:
        form = StudentSignUpForm()
    return render(request, 'register_student.html', {'form': form})

def register_owner(request):
    if request.method == 'POST':
        form = TeacherSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('owner_home')
    else:
        form = TeacherSignUpForm()
    return render(request, 'register_teacher.html', {'form': form})

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})

# Login
def login_request(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user:
                login(request, user)
                # Redirect based on role
                if user.profile.role == 'player':
                    return redirect('player_home')
                elif user.profile.role == 'owner':
                    return redirect('owner_home')
            else:
                messages.error(request, "Invalid username or password")
        else:
            messages.error(request, "Invalid username or password")
    else:
        form = AuthenticationForm()
    
    return render(request, 'playerlogin.html', {'login_form': form})


# Logout
def logout_request(request):
    logout(request)
    return redirect('login')

# Home page (only accessible if logged in)
@login_required
def player_home(request):
    if request.user.profile.role != 'player':
        return redirect('owner_home')
    return render(request, 'browse.html')

@login_required
def owner_home(request):
    if request.user.profile.role != 'owner':
        return redirect('player_home')
    return render(request, 'ownerdashboard.html')





