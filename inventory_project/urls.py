from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import RedirectView

from inventory.views import dashboard_view, product_detail_view, product_list_view

urlpatterns = [
    # Everyone (owner and staff) signs in here and lands on a dashboard that fits their role.
    path('users/login/', auth_views.LoginView.as_view(
        template_name='portal/login.html', redirect_authenticated_user=True), name='portal_login'),
    path('users/logout/', auth_views.LogoutView.as_view(), name='portal_logout'),
    path('users/', dashboard_view, name='dashboard'),
    path('users/products/', product_list_view, name='portal_products'),
    path('users/products/<int:pk>/', product_detail_view, name='portal_product'),

    # Old address, kept so bookmarks still work.
    path('admin/dashboard/', RedirectView.as_view(pattern_name='dashboard')),

    path('admin/', admin.site.urls),
]
