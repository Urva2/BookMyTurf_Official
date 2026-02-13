from django.shortcuts import render, redirect
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import PlayerSignUpForm, OwnerSignUpForm


# Player registration
def register_player(request):
    if request.method == 'POST':
        form = PlayerSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('player_home')
    else:
        form = PlayerSignUpForm()

    return render(request, 'playerregistration.html', {'form': form})


# Owner registration
def register_owner(request):
    if request.method == 'POST':
        form = OwnerSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('owner_home')
    else:
        form = OwnerSignUpForm()

    return render(request, 'ownerregistration.html', {'form': form})


# Login
def login_request(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        # find user by email
        from django.contrib.auth.models import User
        try:
            user_obj = User.objects.get(email=email)
            user = authenticate(request, username=user_obj.username, password=password)
        except User.DoesNotExist:
            user = None

        if user:
            login(request, user)
            if user.profile.role == 'player':
                return redirect('player_home')
            else:
                return redirect('owner_home')
        else:
            messages.error(request, "Invalid email or password")

    return render(request, 'playerlogin.html')



# Logout
def logout_request(request):
    logout(request)
    return redirect('login')


@login_required
def player_home(request):
    return render(request, 'admindashboard.html')


@login_required
def owner_home(request):
    return render(request, 'ownerdashboard.html')
