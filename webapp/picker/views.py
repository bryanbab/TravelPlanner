from django.http import HttpResponse
from django.shortcuts import render


def home(request):
    data = {}
    data['save_location'] = 'here'
    return render(request, 'picker/map.html',data)

def save_location(request):
    if request.method == "POST":
        # Extract latitude and longitude from the POST data
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')

        print("{},{}".format(latitude, longitude))
        return HttpResponse("OK")