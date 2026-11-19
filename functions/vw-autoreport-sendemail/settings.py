class Settings:

    # {0} = date, {1} = Einkaufsorganisation (HTML-escaped by lambda_function.py)
    email_html = """
    <!DOCTYPE html
        PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
    <html xmlns="http://www.w3.org/1999/xhtml">

    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
        <title>IDM AutoReport</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    </head>

    <body style="margin: 0; padding: 0;">
        <table align="center" border="1" cellpadding="0" cellspacing="0" width="450">
            <tr>
                <td align="center" style="padding: 0px 0 0px 0;border-bottom: hidden;border-style: none;position:relative">
                    <a href="https://dqn.bkm.prd.eu.pp.cloud.vwgroup.com/data-quality/genericreport/1200">
                        <img src="https://befnstorage.blob.core.windows.net/befnemail/Template/bkm-email-banner_new.PNG"
                            alt="BKM Input Data Monitor" style="position:relative;width:100%" />
                    </a>
                </td>
            </tr>
            <tr>
                <td bgcolor="#ffffff" style="padding: 20px 30px 40px 30px;border-style: none;">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                        <tr>
                            <td
                                style="text-align:left; padding: 12px 0 8px 0; font-size:16px; line-height:18px; font-family:Calibri, sans-serif; color:#003366; border-bottom: 2px solid #003366;">
                                <strong>Control Center - Auto Report für {} </strong>
                            </td>

                        </tr>
                        <tr>
                            <td
                                style="text-align:left;padding: 10px 0 5px 0;font-size:12px;line-height:14px;font-family:Calibri, sans-serif">
                                <span> Lieber IDM-Nutzer,

                                </span>
                            </td>
                        </tr>
                        <tr>
                            <td
                                style="text-align:left; padding: 10px 0 10px 0;font-size:12px;line-height:14px;font-family:Calibri, sans-serif">
                                <!DOCTYPE html>
                                <html lang="de">

                                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">

                                    im Anhang findest du den automatisch erzeugten Report aus dem Control Center für die Einkaufsorganisation {}. <br>
                                    Falls du dich für Reports von anderen Einkaufsorganisationen interessierst, wende dich an die
                                    <a href="mailto:bkm.input.data.monitor.vwag.r.wob1@volkswagen.de">BKM IDM MailBox</a> oder 
                                    <a href="mailto:matthias.runge@volkswagen.de">Matthias Runge</a>, um dich auf die Email-Liste setzen zu lassen. <br> <br>

                                    Weitere Details findest du auf der Seite des IDM.
                                    </p>

                                </body>

                                </html>


                            </td>
                        </tr>
                        <tr>
                            <td style="text-align:center;padding: 10px 0 20px 0;">
                                <table style="margin:auto; width:30%">
                                    <tr>
                                        <td
                                            style="text-align:center;background-color: #94d523;border-color: #94d523;border: 2px solid #94d523;padding: 15px;border-radius: 10px;">
                                            <a style="display: block;color: white;font-size: 12px;text-decoration: none;"
                                                href="https://dqn.bkm.prd.eu.pp.cloud.vwgroup.com/data-quality/genericreport/1200"> Zum IDM Control Center

                                            </a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td
                                style="text-align:left; padding: 10px 0 10px 0;font-size:12px;line-height:14px;font-family:Calibri, sans-serif">
                                <br> NOTE: This email notification was generated automatically. Responses to automatically
                                generated emails will not be processed. If you would like to contact the BKM IDM team or you
                                need assistance, you can contact us by email or via our Group Wiki website.
                                <br> Technical Support:
                                <a href="mailto:bkm.input.data.monitor.vwag.r.wob1@volkswagen.de">BKM IDM MailBox</a> or
                                <a href="https://volkswagen-net.de/wikis/pages/viewpage.action?pageId=837027503">FAQ Wiki

                                </a>
                            </td>
                        </tr>
                        <tr>
                            <td
                                style="text-align:left;padding: 10px 0 0px 0;font-size:12px;line-height:14px;font-family:Calibri, sans-serif">
                                Viele Grüße

                            </td>
                        </tr>
                        <tr>
                            <td
                                style="text-align:left;padding: 0px 0 25px 0;font-size:12px;line-height:14px;font-family:Calibri, sans-serif">
                                BKM Input Data Monitor Team

                            </td>
                        </tr>
                        <tr>
                            <td style="font-size:9px;line-height:14px;text-align:left;font-family:Calibri, sans-serif;"> The
                                information in this email is confidential and may be legally privileged. If you are not the
                                intended recipient of this message, any review, disclosure, copying, distribution,
                                retention, or any action taken or omitted to be taken in reliance on it is prohibited and
                                may be unlawful. If you are not the intended recipient, please reply to or forward a copy of
                                this message to the sender and delete the message, any attachments, and any copies thereof
                                from your system.

                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
        </td>
        </tr>
        </table>
    </body>

    </html>
    """


settings = Settings()
