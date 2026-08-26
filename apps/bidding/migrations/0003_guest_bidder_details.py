from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('bidding', '0002_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bid',
            name='bidder',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='bids',
                to='gh_accounts.user',
            ),
        ),
        migrations.AddField(
            model_name='bid',
            name='bidder_name',
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name='bid',
            name='bidder_email',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name='bid',
            name='bidder_phone',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='bid',
            name='pickup_notes',
            field=models.TextField(blank=True),
        ),
    ]
