from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('gh_auctions', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='auction',
            name='winner_name',
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name='auction',
            name='winner_email',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name='auction',
            name='winner_phone',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='auction',
            name='winner_pickup_notes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='historicalauction',
            name='winner_name',
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name='historicalauction',
            name='winner_email',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name='historicalauction',
            name='winner_phone',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='historicalauction',
            name='winner_pickup_notes',
            field=models.TextField(blank=True),
        ),
    ]
