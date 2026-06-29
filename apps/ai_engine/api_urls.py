from django.urls import path
from apps.ai_engine.services import api_price_recommendation, api_generate_description, api_demand_forecast

urlpatterns = [
    path('price-recommendation/', api_price_recommendation, name='ai_price_recommendation'),
    path('generate-description/', api_generate_description, name='ai_generate_description'),
    path('demand-forecast/', api_demand_forecast, name='ai_demand_forecast'),
]
